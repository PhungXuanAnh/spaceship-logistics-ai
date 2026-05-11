"""KPI computation — pure functions over an OrderRepository.

Metric definitions
------------------
A *completed* order is one whose final status is known: ``delivered``,
``delayed``, or ``exception``. ``in_transit`` and ``canceled`` are intentionally
excluded from the rate denominators because they have no completion outcome.

    delay_rate   = (delayed + exception) / (delivered + delayed + exception)
    on_time_rate =                 delivered / (delivered + delayed + exception)

(Aliased throughout the codebase as ``DELAYED_STATUSES = {"delayed", "exception"}``
and ``DELIVERED_STATUSES = {"delivered"}``; ``completed = delivered + delayed``
where ``delayed`` already includes ``exception``.)

This is the "Option B" choice from `tmp/narrative.md` §8 — preferred over the
narrower "status == 'delayed' only" definition because the spec example
("delivered late last month") covers both delayed and exception, and over a
delivery-days-vs-SLA rule because no per-carrier SLA table is provided.
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
