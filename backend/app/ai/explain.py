"""Deterministic explanation template — NOT an LLM call."""
from __future__ import annotations

from typing import Any


def explain(plan: dict[str, Any] | None, tool: str, row_count: int, provider: str) -> str:
    if plan is None:
        return f"Used {tool} (provider={provider}). Returned {row_count} row(s)."

    parts: list[str] = []
    metric = plan.get("metric")
    dim = plan.get("dimension")
    if metric and metric != "none":
        parts.append(f"computed {metric}")
    if dim and dim != "none":
        parts.append(f"grouped by {dim}")

    filters_used = []
    for k in ("carrier", "region", "category", "warehouse", "sku", "status"):
        v = plan.get(k)
        if v:
            filters_used.append(f"{k}={','.join(v[:3])}")
    if plan.get("date_from") or plan.get("date_to"):
        filters_used.append(f"date={plan.get('date_from','*')}..{plan.get('date_to','*')}")
    if filters_used:
        parts.append("filtered by " + ", ".join(filters_used))

    parts.append(f"returned {row_count} row(s)")
    parts.append(f"via {tool} ({provider})")
    text = ". ".join(p.capitalize() if i == 0 else p for i, p in enumerate(parts)) + "."

    # Sparse-result hint: when the user asked for Top N but the filter only
    # matches fewer groups, surface that explicitly so the chart doesn't look
    # broken (e.g. "Top 5" returning 1 bar).
    top_n = plan.get("top_n")
    if isinstance(top_n, int) and top_n > 1 and 0 < row_count < top_n:
        text += (
            f" Note: only {row_count} of the requested top {top_n} — "
            f"the current filter matches {row_count} group(s) in the dataset. "
            f"Try broadening the date range or removing a filter for more results."
        )
    return text
