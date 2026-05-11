"""SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    order_date: Mapped[date] = mapped_column(Date, index=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    carrier: Mapped[str] = mapped_column(String(64), index=True)
    origin_city: Mapped[str] = mapped_column(String(128))
    destination_city: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    product_category: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_usd: Mapped[float] = mapped_column(Float)
    order_value_usd: Mapped[float] = mapped_column(Float)
    is_promo: Mapped[bool] = mapped_column(Boolean, default=False)
    promo_discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    region: Mapped[str] = mapped_column(String(32), index=True)
    warehouse: Mapped[str] = mapped_column(String(32), index=True)


class QueryAudit(Base):
    __tablename__ = "query_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_question: Mapped[str] = mapped_column(String(2048))
    intent: Mapped[str] = mapped_column(String(32))  # route | clarify | refuse
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    out_of_scope: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
