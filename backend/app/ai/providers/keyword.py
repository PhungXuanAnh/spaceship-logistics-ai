"""Deterministic regex-based router. Always available, no API key needed.

This is the terminal fallback in the chain AND the default primary for local
demo when no LLM keys are configured. Designed to handle the spec's example
questions verbatim:
  - "Show delayed orders by week for the last 3 months"
  - "Which carrier has the highest delay rate?"
  - "How many orders were delivered late last month?"
  - "Predict demand for SKU X for the next 4 months"
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.ai.contracts import (
    ClarificationRequest,
    ForecastPlan,
    Intent,
    QueryPlan,
    RouterResponse,
)

CARRIERS = {"DHL", "FedEx", "UPS", "USPS", "GLS", "Hermes", "LaserShip", "OnTrac", "Royal Mail"}
REGIONS = {"UK", "US-E", "US-W", "US-C", "EU"}
CATEGORIES = {"PAPER", "CRAYON", "BOOK", "PENCIL", "MARKER", "ART_KIT", "STICKER", "PAINT"}

_REFUSE_PATTERNS = [
    r"\b(drop|delete|truncate|alter)\s+(table|database)",
    r"\bignore\s+previous",
    r"\bsystem\s+prompt",
    r"\b/etc/passwd\b",
    r"169\.254\.169\.254",
    r"\bweather\b",
    r"\bjoke\b",
]


def _today() -> date:
    return date.today()


def _parse_time_window(q: str) -> tuple[date | None, date | None]:
    q = q.lower()
    today = _today()

    m = re.search(r"last\s+(\d+)\s+(day|week|month|year)s?", q)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        return today - timedelta(days=days), today

    if "last week" in q:
        return today - timedelta(days=7), today
    if "last month" in q:
        return today - timedelta(days=30), today
    if "this year" in q or "ytd" in q:
        return date(today.year, 1, 1), today
    if "last year" in q:
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if "all time" in q or "overall" in q:
        return None, None

    # Default to all-time when no time hint (the dataset is full-2025)
    return None, None


def _detect_carriers(q: str) -> list[str]:
    found = [c for c in CARRIERS if c.lower() in q.lower()]
    return found


def _detect_categories(q: str) -> list[str]:
    return [c for c in CATEGORIES if c.lower() in q.lower()]


def _detect_regions(q: str) -> list[str]:
    return [r for r in REGIONS if r.lower() in q.lower()]


class KeywordRouter:
    name = "keyword"

    async def route(self, question: str, schema_hint: dict | None = None) -> RouterResponse:
        q = question.strip()
        ql = q.lower()

        # Refuse adversarial / off-topic
        for pat in _REFUSE_PATTERNS:
            if re.search(pat, ql, re.IGNORECASE):
                return RouterResponse(
                    intent=Intent.REFUSE,
                    refusal_reason="Question is off-topic or potentially unsafe.",
                    rationale="Pattern match against refusal list.",
                )

        if not q or len(q) < 3:
            return RouterResponse(
                intent=Intent.CLARIFY,
                clarification=ClarificationRequest(
                    question="What would you like to know about your logistics data?",
                    suggested_options=[
                        "Show orders over time",
                        "Which carrier has the highest delay rate?",
                        "How many orders were delivered late last month?",
                        "Forecast demand for product PAPER",
                    ],
                ),
                rationale="Empty/too-short question.",
            )

        df, dt = _parse_time_window(ql)
        carriers = _detect_carriers(ql)
        categories = _detect_categories(ql)
        regions = _detect_regions(ql)

        # ---------- FORECAST intent ----------
        if re.search(r"\b(forecast|predict|projection|next\s+\d+\s+(week|month))", ql):
            sku_match = re.search(r"\bsku[\-\s:]?([A-Z]+-\d+)", q, re.IGNORECASE)
            cat_match = re.search(r"(?:category|product)\s+(\w+)", ql)

            horizon_match = re.search(r"next\s+(\d+)\s+(week|month)", ql)
            horizon = 12
            if horizon_match:
                n = int(horizon_match.group(1))
                horizon = n if horizon_match.group(2) == "week" else n * 4

            if sku_match:
                return RouterResponse(
                    intent=Intent.FORECAST,
                    tool="forecast",
                    forecast_plan=ForecastPlan(
                        group_by="sku",
                        group_value=sku_match.group(1).upper(),
                        horizon_weeks=horizon,
                    ),
                    rationale=f"Detected forecast for SKU {sku_match.group(1).upper()}.",
                )
            if categories:
                return RouterResponse(
                    intent=Intent.FORECAST,
                    tool="forecast",
                    forecast_plan=ForecastPlan(
                        group_by="product_category",
                        group_value=categories[0],
                        horizon_weeks=horizon,
                    ),
                    rationale=f"Detected forecast for category {categories[0]}.",
                )
            if cat_match:
                return RouterResponse(
                    intent=Intent.FORECAST,
                    tool="forecast",
                    forecast_plan=ForecastPlan(
                        group_by="product_category",
                        group_value=cat_match.group(1).upper(),
                        horizon_weeks=horizon,
                    ),
                    rationale=f"Detected forecast for category {cat_match.group(1).upper()}.",
                )
            return RouterResponse(
                intent=Intent.CLARIFY,
                clarification=ClarificationRequest(
                    question="Which product category or SKU should I forecast?",
                    suggested_options=["PAPER", "CRAYON", "BOOK", "PENCIL"],
                ),
                rationale="Forecast intent detected but no group specified.",
            )

        # ---------- QUERY intent ----------
        plan = QueryPlan(
            date_from=df,
            date_to=dt,
            carrier=carriers,
            region=regions,
            category=categories,
        )

        # "highest delay rate" / "worst carrier" → top_n by carrier
        if re.search(r"(highest|worst|most|top)\s+(delay|delayed|late)", ql) or re.search(
            r"which\s+\w+\s+has\s+the\s+(most|highest)", ql
        ):
            dim = "carrier"
            if "region" in ql:
                dim = "region"
            elif "warehouse" in ql:
                dim = "warehouse"
            elif "destination" in ql or "city" in ql:
                dim = "destination_city"
            # Honor user-supplied N: "top 10", "top-10", "give me top 20", "10 worst", etc.
            top_n = 5
            n_match = re.search(r"\btop[\s\-]?(\d{1,2})\b", ql) or re.search(
                r"\b(\d{1,2})\s+(worst|highest|most)\b", ql
            )
            if n_match:
                requested = int(n_match.group(1))
                top_n = max(1, min(50, requested))  # clamp to safety.py allow-list range
            plan.dimension = dim
            plan.metric = "delay_rate"
            plan.top_n = top_n
            return RouterResponse(
                intent=Intent.QUERY,
                tool="query",
                query_plan=plan,
                rationale=f"Top-{top_n} {dim} by delay rate.",
            )

        # "by week / month / day" + delayed → time-series of delayed
        if re.search(r"\bdelayed?\b.*\b(by\s+(week|month|day))\b", ql) or re.search(
            r"\b(by\s+(week|month|day))\b.*\bdelayed?\b", ql
        ):
            gran = re.search(r"by\s+(week|month|day)", ql).group(1)
            plan.dimension = "period"
            plan.granularity = gran
            plan.metric = "delayed_count"
            return RouterResponse(
                intent=Intent.QUERY,
                tool="query",
                query_plan=plan,
                rationale=f"Delayed orders over time, granularity={gran}.",
            )

        # "how many orders delivered late" → count delayed (with time window)
        if re.search(r"(how\s+many|count).*(delayed|late)", ql) or re.search(
            r"(delivered\s+late|late\s+orders?)", ql
        ):
            plan.metric = "delayed_count"
            plan.dimension = "none"
            return RouterResponse(
                intent=Intent.QUERY,
                tool="query",
                query_plan=plan,
                rationale="Count of delayed orders within the requested window.",
            )

        # "on-time rate by X" / "delay rate by X" / "compare on-time by region" → breakdown w/ delay_rate
        # MUST come before the generic "by X" branch below — otherwise we lose the metric hint.
        if re.search(r"(on[\s-]?time|delay\s*rate|delivery\s*performance).*\bby\s+\w+", ql) or re.search(
            r"\bcompare\b.*(on[\s-]?time|delay).*\bby\s+\w+", ql
        ):
            for word, dim in [
                ("region", "region"),
                ("carrier", "carrier"),
                ("category", "product_category"),
                ("product", "product_category"),
                ("warehouse", "warehouse"),
                ("destination", "destination_city"),
            ]:
                if re.search(rf"\bby\s+{word}\b", ql):
                    plan.dimension = dim
                    plan.metric = "delay_rate"
                    return RouterResponse(
                        intent=Intent.QUERY,
                        tool="query",
                        query_plan=plan,
                        rationale=f"Compare delay rate across {dim}.",
                    )

        # breakdown by carrier / region / category / warehouse
        for word, dim in [
            ("carrier", "carrier"),
            ("region", "region"),
            ("category", "product_category"),
            ("product", "product_category"),
            ("warehouse", "warehouse"),
            ("destination", "destination_city"),
        ]:
            if re.search(rf"\bby\s+{word}\b", ql) or (f"{word} breakdown" in ql):
                plan.dimension = dim
                plan.metric = "count"
                return RouterResponse(
                    intent=Intent.QUERY,
                    tool="query",
                    query_plan=plan,
                    rationale=f"Breakdown by {dim}.",
                )

        # orders over time
        if re.search(r"(over\s+time|trend|by\s+(week|month|day))", ql) or "volume" in ql:
            gran_m = re.search(r"by\s+(week|month|day)", ql)
            gran = gran_m.group(1) if gran_m else "week"
            plan.dimension = "period"
            plan.granularity = gran
            plan.metric = "count"
            return RouterResponse(
                intent=Intent.QUERY,
                tool="query",
                query_plan=plan,
                rationale=f"Orders volume over time, granularity={gran}.",
            )

        # KPI total orders / delivered / on-time rate
        if re.search(r"(total|how\s+many)\s+orders?", ql):
            plan.metric = "count"
            return RouterResponse(
                intent=Intent.QUERY,
                tool="query",
                query_plan=plan,
                rationale="Count of orders.",
            )
        if re.search(r"on[\s-]?time\s+(rate|delivery|percentage)", ql):
            plan.metric = "on_time_rate"
            return RouterResponse(
                intent=Intent.QUERY,
                tool="query",
                query_plan=plan,
                rationale="On-time delivery rate.",
            )
        if re.search(r"(average|avg)\s+delivery", ql):
            plan.metric = "avg_delivery_days"
            return RouterResponse(
                intent=Intent.QUERY,
                tool="query",
                query_plan=plan,
                rationale="Average delivery days.",
            )

        # Generic show / list orders → KPI summary fallback
        if re.search(r"\b(show|list|give|tell|what|which)\b", ql) and "order" in ql:
            plan.metric = "count"
            return RouterResponse(
                intent=Intent.QUERY,
                tool="query",
                query_plan=plan,
                rationale="Generic orders query — returning summary count.",
            )

        # Last resort: clarify
        return RouterResponse(
            intent=Intent.CLARIFY,
            clarification=ClarificationRequest(
                question="I'm not sure what to compute. Try one of these:",
                suggested_options=[
                    "Show orders over time by week",
                    "Which carrier has the highest delay rate?",
                    "How many orders were delivered late last month?",
                    "Forecast demand for category PAPER",
                ],
            ),
            rationale="No keyword pattern matched.",
        )
