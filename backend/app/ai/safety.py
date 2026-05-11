"""Plan validation: column allow-lists, value sanity, refusal patterns."""
from __future__ import annotations

from app.ai.contracts import QueryPlan

ALLOWED_DIMENSIONS = {
    "carrier", "region", "product_category", "warehouse",
    "status", "destination_city", "period", "none",
}
ALLOWED_METRICS = {
    "count", "delivered_count", "delayed_count",
    "on_time_rate", "avg_delivery_days", "delay_rate", "value_usd",
}


class PlanValidationError(Exception):
    pass


def validate_query_plan(plan: QueryPlan) -> QueryPlan:
    if plan.dimension not in ALLOWED_DIMENSIONS:
        raise PlanValidationError(f"Disallowed dimension: {plan.dimension}")
    if plan.metric not in ALLOWED_METRICS:
        raise PlanValidationError(f"Disallowed metric: {plan.metric}")
    if plan.top_n is not None and not (1 <= plan.top_n <= 50):
        raise PlanValidationError("top_n out of range")
    # All other fields are typed/validated by Pydantic already.
    return plan
