"""Phase-14 v2 engine: POST /api/v2/ask — single-shot Gemini native function-calling.

Same request shape (`{question}`) and same `AskResult` response shape as
`POST /api/ask`. Internally uses `GeminiNativeRouter` directly with
`KeywordRouter` as a terminal exception-only fallback. NO claude, NO second
LLM, NO reflection retry — v2's whole point is that the provider enforces
shape via `function_declarations`.

`AskResult.engine` is set to `"v2-native"` so the FE can show the engine
badge.
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.contracts import AskResult, ChartSpec, Intent
from app.ai.explain import explain
from app.ai.fact_extractor import backfill_plan, extract_facts
from app.ai.providers.gemini_native import GeminiNativeRouter
from app.ai.providers.keyword import KeywordRouter
from app.ai.tools import ForecastTool, QueryTool, SchemaInspectorTool
from app.api.deps import (
    get_current_user,
    get_db_session,
    get_effective_client_id,
    get_repo,
)
from app.api.routes_ask import _pluralize
from app.db.models import QueryAudit, User
from app.prompt_audit import log_prompt
from app.repositories.sqlalchemy_orders import SqlAlchemyOrderRepository
from app.settings import get_settings

router = APIRouter(prefix="/api/v2", tags=["ai-v2"])
logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    question: str


def _build_native_router() -> GeminiNativeRouter | None:
    """Build a GeminiNativeRouter from settings. Returns None if Gemini isn't configured."""
    s = get_settings()
    # Prefer the FALLBACK_* slot (which has the gemini key) but accept LLM_* if it's gemini.
    if s.fallback_provider.lower() == "gemini" and s.fallback_api_key and s.fallback_model:
        return GeminiNativeRouter(
            api_key=s.fallback_api_key,
            model=s.fallback_model,
            base_url=s.fallback_base_url,
        )
    if s.llm_provider.lower() == "gemini" and s.llm_api_key and s.llm_model:
        return GeminiNativeRouter(
            api_key=s.llm_api_key,
            model=s.llm_model,
            base_url=s.llm_base_url,
        )
    return None


@router.post("/ask", response_model=AskResult)
async def ask_v2(
    body: AskRequest,
    request: Request,
    user: User = Depends(get_current_user),
    repo: SqlAlchemyOrderRepository = Depends(get_repo),
    client_id: str | None = Depends(get_effective_client_id),
    db: Session = Depends(get_db_session),
) -> AskResult:
    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    schema_hint = {
        "carriers": repo.distinct_values("carrier"),
        "categories": repo.distinct_values("product_category"),
        "regions": repo.distinct_values("region"),
        "date_range": [d.isoformat() if d else None for d in repo.date_range()],
    }

    native = _build_native_router()
    provider = "gemini-native"
    resp = None
    if native is not None:
        try:
            resp = await native.route(body.question, schema_hint=schema_hint)
        except Exception as e:
            logger.warning("v2-native gemini failed, falling back to keyword: %s", e)
            provider = "keyword"
    else:
        provider = "keyword"

    if resp is None:
        kw = KeywordRouter()
        resp = await kw.route(body.question, schema_hint=schema_hint)

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
        # Same belt-and-suspenders backfill as v1: re-parse the user
        # prompt and fill any plan field the LLM dropped (date_from,
        # region, etc) — particularly important for `Re: "<orig>" — use X.`
        # follow-ups where Gemini sometimes loses the date range from the
        # original prompt while merging the chip value.
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
                "v2 backfilled query_plan from prompt facts: %s (request_id=%s)",
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
            logger.warning("v2 QueryTool failed: %s", e)
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
            logger.warning("v2 ForecastTool failed: %s", e)
            answer = f"Forecast failed: {e}"
            intent = Intent.REFUSE
            out_of_scope = True

    elif intent == Intent.INSPECT:
        tool_used = "schema_inspect"
        column = resp.inspect_column or "carrier"
        tool = SchemaInspectorTool(repo)
        result = tool.invoke(column=column)
        data = [{"value": v} for v in result["values"]]
        values = result["values"]
        shown = values[:10]
        suffix = f" (showing 10 of {len(values)})" if len(values) > 10 else ""
        answer = (
            f"Available {_pluralize(result['column'])} in this dataset: "
            f"{', '.join(shown)}.{suffix}"
        )
        row_count = len(data)

    elif intent == Intent.CLARIFY:
        tool_used = "clarify"
        if resp.clarification and resp.clarification.question:
            answer = resp.clarification.question
        else:
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
        logger.warning("v2 audit insert failed: %s", e)
        db.rollback()

    log_prompt(
        request_id=request_id,
        engine="v2-native",
        user_email=getattr(user, "email", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        question=body.question,
        intent=intent.value,
        tool=tool_used,
        provider=provider,
        duration_ms=duration_ms,
        row_count=row_count,
        out_of_scope=out_of_scope,
        answer=answer,
        data=data,
        plan=plan_dict,
    )

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
        engine="v2-native",
    )
