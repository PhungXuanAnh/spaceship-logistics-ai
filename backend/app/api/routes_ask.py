"""POST /api/ask — natural-language query routing."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai import build_router_chain
from app.ai.contracts import AskResult, ChartSpec, Intent
from app.ai.explain import explain
from app.ai.fact_extractor import backfill_plan, extract_facts
from app.ai.tools import ForecastTool, QueryTool, SchemaInspectorTool
from app.api.deps import get_db_session, get_effective_client_id, get_repo
from app.db.models import QueryAudit, User
from app.api.deps import get_current_user
from app.repositories.sqlalchemy_orders import SqlAlchemyOrderRepository

router = APIRouter(prefix="/api", tags=["ai"])
logger = logging.getLogger(__name__)

# Pretty plural forms for the schema_inspect answer string. Naive `+ "s"`
# yields awkward output like "product_categorys" / "statuss".
_COLUMN_PLURALS = {
    "carrier": "carriers",
    "region": "regions",
    "product_category": "product categories",
    "warehouse": "warehouses",
    "status": "statuses",
}


def _pluralize(column: str) -> str:
    return _COLUMN_PLURALS.get(column, f"{column}s")


class AskRequest(BaseModel):
    question: str


@router.post("/ask", response_model=AskResult)
async def ask(
    body: AskRequest,
    request: Request,
    user: User = Depends(get_current_user),
    repo: SqlAlchemyOrderRepository = Depends(get_repo),
    client_id: str | None = Depends(get_effective_client_id),
    db: Session = Depends(get_db_session),
) -> AskResult:
    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    chain = build_router_chain()
    schema_hint = {
        "carriers": repo.distinct_values("carrier"),
        "categories": repo.distinct_values("product_category"),
        "regions": repo.distinct_values("region"),
        "date_range": [d.isoformat() if d else None for d in repo.date_range()],
    }

    try:
        resp, provider, _meta = await chain.route(body.question, schema_hint=schema_hint)
    except Exception as e:
        logger.exception("Router chain failed: %s", e)
        return AskResult(
            intent=Intent.REFUSE,
            tool_used="none",
            answer=f"Internal error: {type(e).__name__}",
            data=[],
            chart_spec=None,
            plan=None,
            explanation="Router chain failed",
            provider_used="error",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            request_id=request_id,
        )

    intent = resp.intent
    tool_used = "none"
    answer = ""
    data: list[dict] = []
    chart_spec: ChartSpec | None = None
    plan_dict: dict | None = None
    out_of_scope = False
    row_count = 0
    clarification = resp.clarification

    if intent == Intent.QUERY and resp.query_plan:
        tool_used = "query"
        # Belt-and-suspenders: even with a tightened system prompt the LLM
        # occasionally drops a date / region / carrier filter when it
        # rewrites a `Re: "<orig>" — use X.` follow-up. Re-parse the user
        # prompt and backfill any empty plan fields from the literal text.
        # Pin the year off the dataset's actual range, not "today", so
        # "in October" on a 2025 dataset → 2025-10-01..2025-10-31.
        dataset_range = repo.date_range()
        default_year = dataset_range[1].year if dataset_range[1] else None
        facts = extract_facts(
            body.question,
            default_year=default_year,
            anchor=dataset_range[1],
        )
        plan_dump = resp.query_plan.model_dump(mode="json")
        backfilled, filled_keys = backfill_plan(plan_dump, facts, dataset_range=dataset_range)
        if filled_keys:
            logger.info(
                "Backfilled query_plan from prompt facts: %s (request_id=%s)",
                filled_keys, request_id,
            )
            from app.ai.contracts import QueryPlan as _QueryPlan
            resp.query_plan = _QueryPlan.model_validate(backfilled)
        plan_dict = resp.query_plan.model_dump(mode="json")
        try:
            tool = QueryTool(repo, tenant_client_id=client_id)
            result = tool.invoke(resp.query_plan)
            data = result["rows"]
            answer = result["answer"]
            chart_spec = ChartSpec(**result["chart_spec"])
            row_count = result["row_count"]
        except Exception as e:
            logger.warning("QueryTool failed: %s", e)
            answer = f"Query failed: {e}"
            intent = Intent.REFUSE
            out_of_scope = True

    elif intent == Intent.FORECAST and resp.forecast_plan:
        tool_used = "forecast"
        plan_dict = resp.forecast_plan.model_dump(mode="json")
        try:
            tool = ForecastTool(repo, tenant_client_id=client_id)
            result = tool.invoke(resp.forecast_plan)
            data = result["rows"]
            answer = result["answer"]
            chart_spec = ChartSpec(**result["chart_spec"])
            row_count = result["row_count"]
        except Exception as e:
            logger.warning("ForecastTool failed: %s", e)
            answer = f"Forecast failed: {e}"
            intent = Intent.REFUSE
            out_of_scope = True

    elif intent == Intent.INSPECT:
        tool_used = "schema_inspect"
        column = resp.inspect_column or "carrier"
        tool = SchemaInspectorTool(repo)
        result = tool.invoke(column=column)
        data = [{"value": v} for v in result["values"]]
        answer = (
            f"I can't validate the value you mentioned. Available {_pluralize(result['column'])}: "
            f"{', '.join(result['values'][:10])}..."
        )
        row_count = len(data)

    elif intent == Intent.CLARIFY:
        tool_used = "clarify"
        if resp.clarification and resp.clarification.question:
            answer = resp.clarification.question
        else:
            # LLM returned clarify intent without filling the clarification
            # field. Synthesize a generic prompt so the UI always has
            # something to render instead of a blank box.
            from app.ai.contracts import ClarificationRequest

            clarification = ClarificationRequest(
                question=(
                    "I need a bit more detail to answer this. Could you specify a "
                    "time range, a metric, or a dimension?"
                ),
                suggested_options=[
                    "this quarter",
                    "last 30 days",
                    "by carrier",
                    "by region",
                ],
            )
            answer = clarification.question

    else:  # REFUSE
        tool_used = "none"
        answer = resp.refusal_reason or "I can't help with that. Try a logistics analytics question."
        out_of_scope = True

    duration_ms = int((time.perf_counter() - t0) * 1000)
    explanation = explain(plan_dict, tool_used, row_count, provider)

    # Audit row
    try:
        db.add(
            QueryAudit(
                request_id=request_id,
                user_id=user.id,
                user_question=body.question[:2000],
                intent=intent.value,
                tool_name=tool_used,
                provider_used=provider,
                duration_ms=duration_ms,
                row_count=row_count,
                out_of_scope=out_of_scope,
            )
        )
        db.commit()
    except Exception as e:
        logger.warning("Audit insert failed: %s", e)
        db.rollback()

    return AskResult(
        intent=intent,
        tool_used=tool_used,
        answer=answer,
        data=data,
        chart_spec=chart_spec,
        plan=plan_dict,
        explanation=explanation,
        provider_used=provider,
        duration_ms=duration_ms,
        request_id=request_id,
        clarification=clarification,
    )
