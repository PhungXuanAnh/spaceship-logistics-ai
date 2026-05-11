"""Forecasting smoke tests."""
from __future__ import annotations

from app.analytics.forecast import forecast_demand
from app.repositories.base import Filters
from app.repositories.sqlalchemy_orders import SqlAlchemyOrderRepository


def test_forecast_paper_category(db_session):
    repo = SqlAlchemyOrderRepository(db_session)
    result = forecast_demand(repo, Filters(), "product_category", "PAPER", horizon=8)
    assert result["history_weeks"] > 0
    assert len(result["forecast"]) == 8
    assert "method" in result
    assert result["inventory_recommendation_per_week"] >= 0
    # Forecast values are non-negative
    assert all(f["value"] >= 0 for f in result["forecast"])


def test_forecast_handles_empty_series(db_session):
    repo = SqlAlchemyOrderRepository(db_session)
    result = forecast_demand(
        repo, Filters(), "product_category", "DOES_NOT_EXIST", horizon=4
    )
    assert result["history_weeks"] == 0
    # Should still return a forecast (zeros from MA fallback)
    assert len(result["forecast"]) == 4
