"""Deterministic chart-spec derivation: maps (dimension, metric) → ChartType."""
from __future__ import annotations

from enum import Enum
from typing import Any


class ChartType(str, Enum):
    LINE = "line"
    BAR = "bar"
    GROUPED_BAR = "grouped_bar"
    STACKED_BAR = "stacked_bar"
    STAT = "stat"
    TABLE = "table"
    AREA = "area"


def derive_chart_spec(
    intent: str,
    dimension: str | None,
    metric: str | None,
    n_rows: int,
) -> dict[str, Any]:
    """Pick a chart type based on the shape of the result, not LLM choice.

    Rules:
      - intent == 'kpi' → STAT
      - dimension is a date/period → LINE (or AREA for cumulative)
      - dimension == status with multi-bucket → STACKED_BAR
      - dimension nominal + 1 metric → BAR
      - dimension nominal + 2+ metrics → GROUPED_BAR
      - n_rows > 25 → TABLE
    """
    # Map LLM/router metric names to actual row keys produced by analytics.breakdowns.
    # NOTE: breakdown_by() returns rows keyed as {dimension, total, delivered, delayed,
    # value_usd, delay_rate}. There is NO "count" column — "count" gets normalized to
    # "total" so the FE finds the data. Same for the *_count forms and on_time_rate.
    _METRIC_TO_ROW_KEY = {
        "count": "total",
        "delivered_count": "delivered",
        "delayed_count": "delayed",
        "on_time_rate": "delay_rate",  # complement; FE chart shows delay_rate
        None: "total",
    }
    y_key = _METRIC_TO_ROW_KEY.get(metric, metric or "total")

    if intent == "kpi":
        return {"type": ChartType.STAT, "x": None, "y": y_key}

    if intent == "forecast":
        return {"type": ChartType.LINE, "x": "period", "y": "value", "extras": ["lower", "upper"]}

    if dimension in {"period", "order_date", "delivery_date"}:
        return {"type": ChartType.LINE, "x": dimension, "y": y_key}

    if n_rows > 25:
        return {"type": ChartType.TABLE, "x": dimension, "y": y_key}

    if dimension == "status":
        return {"type": ChartType.STACKED_BAR, "x": dimension, "y": y_key}

    if metric == "delay_breakdown":
        return {"type": ChartType.STACKED_BAR, "x": dimension, "y": ["delivered", "delayed"]}

    return {"type": ChartType.BAR, "x": dimension or "_", "y": y_key}
