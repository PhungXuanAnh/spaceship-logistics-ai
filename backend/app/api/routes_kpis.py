"""KPI + chart endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_filters, get_repo
from app.analytics import breakdowns, kpis
from app.repositories.base import Filters
from app.repositories.sqlalchemy_orders import SqlAlchemyOrderRepository

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/kpis")
def get_kpis(
    filters: Filters = Depends(get_filters),
    repo: SqlAlchemyOrderRepository = Depends(get_repo),
):
    return kpis.compute_kpis(repo, filters)


@router.get("/charts/orders-over-time")
def chart_orders_over_time(
    granularity: str = Query(default="week", pattern="^(day|week|month)$"),
    filters: Filters = Depends(get_filters),
    repo: SqlAlchemyOrderRepository = Depends(get_repo),
):
    return {
        "granularity": granularity,
        "rows": breakdowns.orders_over_time(repo, filters, granularity),
    }


@router.get("/charts/breakdown")
def chart_breakdown(
    dimension: str = Query(default="carrier"),
    filters: Filters = Depends(get_filters),
    repo: SqlAlchemyOrderRepository = Depends(get_repo),
):
    return {"dimension": dimension, "rows": breakdowns.breakdown_by(repo, filters, dimension)}


@router.get("/charts/top")
def chart_top(
    dimension: str = Query(default="carrier"),
    metric: str = Query(default="delay_rate"),
    n: int = Query(default=5, ge=1, le=20),
    filters: Filters = Depends(get_filters),
    repo: SqlAlchemyOrderRepository = Depends(get_repo),
):
    return {
        "dimension": dimension,
        "metric": metric,
        "rows": breakdowns.top_n_by(repo, filters, dimension, metric, n),
    }


@router.get("/data/preview")
def preview(
    limit: int = Query(default=50, ge=1, le=500),
    filters: Filters = Depends(get_filters),
    repo: SqlAlchemyOrderRepository = Depends(get_repo),
):
    rows = repo.fetch_orders(filters)[:limit]
    # Serialize dates
    for r in rows:
        for k in ("order_date", "delivery_date"):
            if r.get(k) is not None:
                r[k] = r[k].isoformat()
    return {"rows": rows, "total_returned": len(rows)}


@router.get("/data/distinct/{column}")
def distinct(
    column: str,
    repo: SqlAlchemyOrderRepository = Depends(get_repo),
):
    return {"column": column, "values": repo.distinct_values(column)}


@router.get("/data/info")
def data_info(repo: SqlAlchemyOrderRepository = Depends(get_repo)):
    """Lightweight dataset metadata for the UI.

    The frontend renders the demo's "today" badge from `date_range[1]` so
    users understand that relative phrases like "last 3 months" are
    anchored to the dataset's max date, not wall-clock time.
    """
    rng = repo.date_range()
    return {
        "date_range": [d.isoformat() if d else None for d in rng],
    }
