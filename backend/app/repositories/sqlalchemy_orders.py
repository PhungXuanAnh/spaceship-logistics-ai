"""SQLAlchemy implementation of OrderRepository."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import Session

from app.db.models import Order
from app.repositories.base import Filters, OrderRepository


_ALLOWED_DISTINCT_COLUMNS = {
    "carrier",
    "region",
    "product_category",
    "warehouse",
    "status",
    "client_id",
}


class SqlAlchemyOrderRepository(OrderRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _build_where(self, filters: Filters) -> list[Any]:
        conds: list[Any] = []
        if filters.client_id:
            conds.append(Order.client_id == filters.client_id)
        if filters.date_from:
            conds.append(Order.order_date >= filters.date_from)
        if filters.date_to:
            conds.append(Order.order_date <= filters.date_to)
        if filters.carrier:
            conds.append(Order.carrier.in_(filters.carrier))
        if filters.region:
            conds.append(Order.region.in_(filters.region))
        if filters.category:
            conds.append(Order.product_category.in_(filters.category))
        if filters.warehouse:
            conds.append(Order.warehouse.in_(filters.warehouse))
        if filters.sku:
            conds.append(Order.sku.in_(filters.sku))
        if filters.status:
            conds.append(Order.status.in_(filters.status))
        return conds

    def fetch_orders(self, filters: Filters) -> list[dict[str, Any]]:
        conds = self._build_where(filters)
        stmt = select(Order)
        if conds:
            stmt = stmt.where(and_(*conds))
        rows = self._session.execute(stmt).scalars().all()
        return [
            {
                "client_id": r.client_id,
                "order_id": r.order_id,
                "order_date": r.order_date,
                "delivery_date": r.delivery_date,
                "carrier": r.carrier,
                "origin_city": r.origin_city,
                "destination_city": r.destination_city,
                "status": r.status,
                "sku": r.sku,
                "product_category": r.product_category,
                "quantity": r.quantity,
                "unit_price_usd": r.unit_price_usd,
                "order_value_usd": r.order_value_usd,
                "is_promo": r.is_promo,
                "promo_discount_pct": r.promo_discount_pct,
                "region": r.region,
                "warehouse": r.warehouse,
            }
            for r in rows
        ]

    def distinct_values(self, column: str) -> list[str]:
        if column not in _ALLOWED_DISTINCT_COLUMNS:
            return []
        col = getattr(Order, column)
        return sorted(
            v for (v,) in self._session.execute(select(distinct(col))).all() if v is not None
        )

    def date_range(self) -> tuple[date | None, date | None]:
        row = self._session.execute(
            select(func.min(Order.order_date), func.max(Order.order_date))
        ).first()
        if row is None:
            return None, None
        return row[0], row[1]
