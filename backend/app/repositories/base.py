"""OrderRepository Protocol + filter contract.

Pure analytics modules depend on this interface only — no SQLAlchemy reaches
analytics/ or ai/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


@dataclass
class Filters:
    """Filters applied to every analytical query.

    `client_id` is always set by the API layer based on the current user/tenant
    and must not be overridable by user input.
    """

    client_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    carrier: list[str] = field(default_factory=list)
    region: list[str] = field(default_factory=list)
    category: list[str] = field(default_factory=list)
    warehouse: list[str] = field(default_factory=list)
    sku: list[str] = field(default_factory=list)
    status: list[str] = field(default_factory=list)


class OrderRepository(Protocol):
    """Domain interface — analytics depend on this, not on SQLAlchemy."""

    def fetch_orders(self, filters: Filters) -> list[dict[str, Any]]:
        """Return orders matching filters as plain dicts (analytics-friendly)."""
        ...

    def distinct_values(self, column: str) -> list[str]:
        """Distinct values for a column (low-cardinality fields only)."""
        ...

    def date_range(self) -> tuple[date | None, date | None]:
        """Min and max order_date in the dataset (post-filter scope)."""
        ...
