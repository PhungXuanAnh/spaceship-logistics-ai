"""KPI + breakdowns + chart_spec smoke tests."""
from __future__ import annotations

from app.analytics import breakdowns, kpis
from app.analytics.chart_spec import ChartType, derive_chart_spec
from app.repositories.base import Filters
from app.repositories.sqlalchemy_orders import SqlAlchemyOrderRepository


def test_kpis_with_carrier_filter(db_session):
    repo = SqlAlchemyOrderRepository(db_session)
    f = Filters(carrier=["DHL"])
    k = kpis.compute_kpis(repo, f)
    assert k["total_orders"] > 0
    # Confirm filter actually narrowed
    all_k = kpis.compute_kpis(repo, Filters())
    assert k["total_orders"] < all_k["total_orders"]


def test_kpis_empty_filter_returns_zero(db_session):
    repo = SqlAlchemyOrderRepository(db_session)
    f = Filters(carrier=["DOES_NOT_EXIST"])
    k = kpis.compute_kpis(repo, f)
    assert k["total_orders"] == 0
    assert k["on_time_delivery_rate"] == 0.0  # division-by-zero guard


def test_kpis_tenant_isolation(db_session):
    """client_id filter is applied + tenants are disjoint (no row leak across tenants).

    Pinned against the demo CSV: CL-1001 has 35 orders, CL-1002 has 31, and the
    total across all 30 client_ids is 400. If the filter were silently ignored,
    both queries would return 400. If rows leaked across tenants, the per-tenant
    sum would exceed 400.
    """
    repo = SqlAlchemyOrderRepository(db_session)
    k_a = kpis.compute_kpis(repo, Filters(client_id="CL-1001"))
    k_b = kpis.compute_kpis(repo, Filters(client_id="CL-1002"))
    k_all = kpis.compute_kpis(repo, Filters())
    assert k_a["total_orders"] == 35
    assert k_b["total_orders"] == 31
    assert k_all["total_orders"] == 400
    # Disjointness sanity check: any single-tenant slice must be strictly less
    # than the global total (if tenants were leaking, one slice could == 400).
    assert k_a["total_orders"] < k_all["total_orders"]
    assert k_b["total_orders"] < k_all["total_orders"]


def test_orders_over_time_weekly(db_session):
    repo = SqlAlchemyOrderRepository(db_session)
    rows = breakdowns.orders_over_time(repo, Filters(), "week")
    assert len(rows) > 0
    total = sum(r["total"] for r in rows)
    assert total == 400


def test_chart_spec_kpi_returns_stat():
    spec = derive_chart_spec("kpi", None, "count", 1)
    assert spec["type"] == ChartType.STAT


def test_chart_spec_period_returns_line():
    spec = derive_chart_spec("query", "period", "count", 30)
    assert spec["type"] == ChartType.LINE


def test_chart_spec_large_returns_table():
    spec = derive_chart_spec("query", "destination_city", "count", 100)
    assert spec["type"] == ChartType.TABLE
