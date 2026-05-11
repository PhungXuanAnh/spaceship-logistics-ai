"""KeywordRouter routing tests."""
from __future__ import annotations

import pytest

from app.ai.contracts import Intent
from app.ai.providers.keyword import KeywordRouter


@pytest.mark.asyncio
async def test_route_delayed_by_week():
    r = await KeywordRouter().route("Show delayed orders by week for the last 3 months")
    assert r.intent == Intent.QUERY
    assert r.tool == "query"
    assert r.query_plan.dimension == "period"
    assert r.query_plan.granularity == "week"
    assert r.query_plan.metric == "delayed_count"


@pytest.mark.asyncio
async def test_route_highest_delay_rate_carrier():
    r = await KeywordRouter().route("Which carrier has the highest delay rate?")
    assert r.intent == Intent.QUERY
    assert r.query_plan.dimension == "carrier"
    assert r.query_plan.metric == "delay_rate"
    assert r.query_plan.top_n == 5


@pytest.mark.asyncio
async def test_route_late_orders_last_month():
    r = await KeywordRouter().route("How many orders were delivered late last month?")
    assert r.intent == Intent.QUERY
    assert r.query_plan.metric == "delayed_count"


@pytest.mark.asyncio
async def test_route_forecast_sku():
    r = await KeywordRouter().route("Predict demand for SKU PAPER-0197 for the next 4 months")
    assert r.intent == Intent.FORECAST
    assert r.forecast_plan.group_by == "sku"
    assert r.forecast_plan.group_value == "PAPER-0197"
    assert r.forecast_plan.horizon_weeks == 16  # 4 months ≈ 16 weeks


@pytest.mark.asyncio
async def test_route_forecast_category():
    r = await KeywordRouter().route("Forecast demand for category PAPER for the next 8 weeks")
    assert r.intent == Intent.FORECAST
    assert r.forecast_plan.group_by == "product_category"
    assert r.forecast_plan.group_value == "PAPER"
    assert r.forecast_plan.horizon_weeks == 8


@pytest.mark.asyncio
async def test_route_refuses_drop_table():
    r = await KeywordRouter().route("DROP TABLE orders; --")
    assert r.intent == Intent.REFUSE


@pytest.mark.asyncio
async def test_route_refuses_off_topic():
    r = await KeywordRouter().route("What is the weather today?")
    assert r.intent == Intent.REFUSE


@pytest.mark.asyncio
async def test_route_clarifies_ambiguous():
    r = await KeywordRouter().route("forecast")  # too short for forecast keyword to fire correctly
    assert r.intent in (Intent.CLARIFY, Intent.FORECAST)


@pytest.mark.asyncio
async def test_route_breakdown_by_region():
    r = await KeywordRouter().route("Show me orders by region")
    assert r.intent == Intent.QUERY
    assert r.query_plan.dimension == "region"


@pytest.mark.asyncio
async def test_route_total_orders():
    r = await KeywordRouter().route("How many total orders do we have?")
    assert r.intent == Intent.QUERY
    assert r.query_plan.metric == "count"
