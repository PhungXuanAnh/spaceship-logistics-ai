"""KPI computation — pure functions over an OrderRepository.

Delayed rule: status IN ('delayed', 'exception') (Option B per narrative §8).
"""
from __future__ import annotations

from typing import Any

from app.repositories.base import Filters, OrderRepository

DELAYED_STATUSES = {"delayed", "exception"}
DELIVERED_STATUSES = {"delivered"}


def _delivery_days(o: dict[str, Any]) -> int | None:
    if o.get("delivery_date") is None or o.get("order_date") is None:
        return None
    return (o["delivery_date"] - o["order_date"]).days


def compute_kpis(repo: OrderRepository, filters: Filters) -> dict[str, Any]:
    orders = repo.fetch_orders(filters)
    total = len(orders)
    delivered = sum(1 for o in orders if o["status"] in DELIVERED_STATUSES)
    delayed = sum(1 for o in orders if o["status"] in DELAYED_STATUSES)
    completed = delivered + delayed  # only completed orders count toward on-time rate

    on_time_rate = (delivered / completed) if completed else 0.0

    delivery_days = [d for o in orders if (d := _delivery_days(o)) is not None]
    avg_delivery_days = (sum(delivery_days) / len(delivery_days)) if delivery_days else 0.0

    return {
        "total_orders": total,
        "delivered_orders": delivered,
        "delayed_orders": delayed,
        "on_time_delivery_rate": round(on_time_rate, 4),
        "avg_delivery_days": round(avg_delivery_days, 2),
    }
