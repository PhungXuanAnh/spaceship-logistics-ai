"""Phase-13 synonym remap layer.

LLMs sometimes emit semantically-correct but enum-illegal values like
`metric: "delayed_orders"` (instead of `delayed_count`) or
`dimension: "order_date"` (instead of `period`). We catch the most common
miss-mappings at the JSON-text layer BEFORE Pydantic validation runs,
which spares the reflection-retry round-trip for the obvious cases.

This is a pure string-substitution pass over the raw LLM JSON text — it
does NOT touch the JSON structure, so it can't accidentally corrupt a
valid response. Mapping is intentionally conservative: only aliases we
have observed in real LLM output go in here.
"""
from __future__ import annotations

import re

# value→canonical mappings keyed by JSON field. Order matters within each
# group: longer keys first so partial matches don't shadow longer ones.
_VALUE_REMAPS: dict[str, dict[str, str]] = {
    "metric": {
        "delayed_orders": "delayed_count",
        "delayed_order_count": "delayed_count",
        "delayed_shipments": "delayed_count",
        "shipments_delayed": "delayed_count",
        "delivered_orders": "delivered_count",
        "delivered_shipments": "delivered_count",
        "shipments": "count",
        "orders": "count",
        "order_count": "count",
        "shipment_count": "count",
        "on_time_percentage": "on_time_rate",
        "on_time_pct": "on_time_rate",
        "ontime_rate": "on_time_rate",
        "ontime_percentage": "on_time_rate",
        "delay_percentage": "delay_rate",
        "delay_pct": "delay_rate",
        "average_delivery_days": "avg_delivery_days",
        "avg_delivery_time": "avg_delivery_days",
        "average_delivery_time": "avg_delivery_days",
        "delivery_time": "avg_delivery_days",
        "total_value": "value_usd",
        "revenue": "value_usd",
        "order_value": "value_usd",
    },
    "dimension": {
        "order_date": "period",
        "delivery_date": "period",
        "date": "period",
        "week": "period",
        "month": "period",
        "day": "period",
        "time": "period",
        "category": "product_category",
        "product": "product_category",
        "city": "destination_city",
        "destination": "destination_city",
        "courier": "carrier",
        "shipper": "carrier",
    },
    "granularity": {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
    },
    "intent": {
        "answer": "query",
        "respond": "query",
        "predict": "forecast",
        "predicting": "forecast",
        "ask": "clarify",
        "ask_user": "clarify",
        "decline": "refuse",
        "reject": "refuse",
    },
}

# Field-name remaps (LLM outputs `clarification.message` instead of
# `clarification.question`, etc.).
_KEY_REMAPS: dict[str, str] = {
    '"message"': '"question"',  # only inside clarification blocks (safe — Pydantic ignores extra keys)
    '"options"': '"suggested_options"',
    '"chips"': '"suggested_options"',
    '"q_plan"': '"query_plan"',
    '"f_plan"': '"forecast_plan"',
}


def normalize_router_payload(text: str) -> str:
    """Apply known LLM-emit → canonical-enum remaps to a raw JSON text blob.

    Pure string transform; idempotent; safe to run on already-canonical text.
    """
    if not text:
        return text

    # Field-name remaps (whole-word JSON keys).
    out = text
    for old, new in _KEY_REMAPS.items():
        out = out.replace(old, new)

    # Value remaps: only inside `"<field>": "<value>"` pairs so we don't
    # accidentally rewrite legitimate text inside other fields (rationale, etc.).
    for field, mapping in _VALUE_REMAPS.items():
        for alias, canonical in mapping.items():
            # Match: "field": "alias"  (allow whitespace + optional surrounding ws/case-insensitive value)
            pattern = re.compile(
                rf'("{re.escape(field)}"\s*:\s*")'  # group 1: "field": "
                rf'{re.escape(alias)}'              # alias literal (we keep it exact)
                rf'(")',                             # group 2: closing "
                flags=re.IGNORECASE,
            )
            out = pattern.sub(rf'\g<1>{canonical}\g<2>', out)

    return out
