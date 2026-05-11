"""Breakdowns and time-series — pure functions over an OrderRepository."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.analytics.kpis import DELAYED_STATUSES, DELIVERED_STATUSES
from app.repositories.base import Filters, OrderRepository


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _bucket_key(d: date, granularity: str, min_date: date | None = None) -> str:
    if granularity == "day":
        return d.isoformat()
    if granularity == "month":
        # Clamp month label to start of filter window so a Dec 30 anchor
        # bucketed by month doesn't show a leading "M-01" for the first
        # partial bucket. Same idea as week clamping below.
        first_of_month = date(d.year, d.month, 1)
        if min_date is not None and first_of_month < min_date:
            return f"{min_date.year}-{min_date.month:02d}"
        return f"{d.year}-{d.month:02d}"
    # week (default): align to ISO Monday, then clamp to filter window so
    # an order on Wed Oct 1 doesn't get labelled as the week of Mon Sep 29
    # when the user asked for "last 3 months" → date_from=Oct 1.
    ws = _week_start(d)
    if min_date is not None and ws < min_date:
        ws = min_date
    return ws.isoformat()


def orders_over_time(
    repo: OrderRepository, filters: Filters, granularity: str = "week"
) -> list[dict[str, Any]]:
    orders = repo.fetch_orders(filters)
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "delivered": 0, "delayed": 0})
    min_date = getattr(filters, "date_from", None)
    for o in orders:
        key = _bucket_key(o["order_date"], granularity, min_date=min_date)
        buckets[key]["total"] += 1
        if o["status"] in DELIVERED_STATUSES:
            buckets[key]["delivered"] += 1
        elif o["status"] in DELAYED_STATUSES:
            buckets[key]["delayed"] += 1
    return [
        {"period": k, **v} for k, v in sorted(buckets.items())
    ]


def breakdown_by(
    repo: OrderRepository, filters: Filters, dimension: str
) -> list[dict[str, Any]]:
    """Aggregate counts by dimension (carrier, region, product_category, warehouse, status)."""
    valid = {"carrier", "region", "product_category", "warehouse", "status", "destination_city"}
    if dimension not in valid:
        raise ValueError(f"Invalid dimension: {dimension}")

    orders = repo.fetch_orders(filters)
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "delivered": 0, "delayed": 0, "value_usd": 0.0}
    )
    for o in orders:
        key = str(o[dimension])
        b = buckets[key]
        b["total"] += 1
        if o["status"] in DELIVERED_STATUSES:
            b["delivered"] += 1
        elif o["status"] in DELAYED_STATUSES:
            b["delayed"] += 1
        b["value_usd"] += float(o["order_value_usd"])

    result = []
    for k, v in buckets.items():
        completed = v["delivered"] + v["delayed"]
        v["delay_rate"] = round(v["delayed"] / completed, 4) if completed else 0.0
        v["value_usd"] = round(v["value_usd"], 2)
        result.append({dimension: k, **v})
    result.sort(key=lambda r: r["total"], reverse=True)
    return result


def top_n_by(
    repo: OrderRepository,
    filters: Filters,
    dimension: str,
    metric: str = "delay_rate",
    n: int = 5,
) -> list[dict[str, Any]]:
    rows = breakdown_by(repo, filters, dimension)
    if metric not in {"delay_rate", "total", "delivered", "delayed", "value_usd"}:
        metric = "total"
    # For delay_rate require at least 5 completed orders to be meaningful
    if metric == "delay_rate":
        rows = [r for r in rows if (r["delivered"] + r["delayed"]) >= 5]
    rows.sort(key=lambda r: r[metric], reverse=True)
    return rows[:n]
