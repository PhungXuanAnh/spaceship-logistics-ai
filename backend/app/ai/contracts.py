"""Typed contracts for the AI orchestration layer.

Pure pydantic — no FastAPI, no SQLAlchemy.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field


class Intent(str, Enum):
    QUERY = "query"
    FORECAST = "forecast"
    CLARIFY = "clarify"
    REFUSE = "refuse"
    INSPECT = "inspect"


class QueryPlan(BaseModel):
    """Validated query plan — never raw SQL, never user-controlled identifiers."""

    metric: Literal[
        "count",
        "delivered_count",
        "delayed_count",
        "on_time_rate",
        "avg_delivery_days",
        "delay_rate",
        "value_usd",
    ] = "count"
    dimension: Literal[
        "carrier",
        "region",
        "product_category",
        "warehouse",
        "status",
        "destination_city",
        "period",
        "none",
    ] = "none"
    granularity: Literal["day", "week", "month"] = "week"
    top_n: int | None = Field(default=None, ge=1, le=50)
    date_from: date | None = None
    date_to: date | None = None
    carrier: list[str] = Field(default_factory=list)
    region: list[str] = Field(default_factory=list)
    category: list[str] = Field(default_factory=list)
    warehouse: list[str] = Field(default_factory=list)
    sku: list[str] = Field(default_factory=list)
    status: list[str] = Field(default_factory=list)


class ForecastPlan(BaseModel):
    group_by: Literal["product_category", "sku"] = "product_category"
    group_value: str
    horizon_weeks: int = Field(default=12, ge=1, le=52)
    date_from: date | None = None
    date_to: date | None = None


class ClarificationRequest(BaseModel):
    question: str
    # Canonical name is `suggested_options`; legacy LLM outputs sometimes emit
    # `chips` or `options` so we accept those as aliases.
    suggested_options: list[str] = Field(
        default_factory=list,
        max_length=4,
        validation_alias=AliasChoices("suggested_options", "chips", "options"),
        serialization_alias="suggested_options",
    )

    model_config = {"populate_by_name": True}


class RouterResponse(BaseModel):
    """LLM-facing response shape (also used by KeywordRouter)."""

    intent: Intent
    tool: Literal["query", "forecast", "schema_inspect", "none"] = "none"
    query_plan: QueryPlan | None = None
    forecast_plan: ForecastPlan | None = None
    clarification: ClarificationRequest | None = None
    refusal_reason: str | None = None
    rationale: str | None = None
    inspect_column: Literal["carrier", "region", "product_category", "warehouse", "status"] | None = None


class ChartSpec(BaseModel):
    type: str
    x: str | None = None
    y: Any = None
    extras: list[str] = Field(default_factory=list)


class AskResult(BaseModel):
    intent: Intent
    tool_used: str
    answer: str
    data: list[dict[str, Any]] = Field(default_factory=list)
    chart_spec: ChartSpec | None = None
    plan: dict[str, Any] | None = None
    explanation: str
    provider_used: str
    duration_ms: int
    request_id: str
    clarification: ClarificationRequest | None = None
    # Which orchestration engine produced this answer.
    engine: Literal["v1-cascade", "v2-native"] = "v1-cascade"
