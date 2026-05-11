"""Forecasting tool: moving average baseline + Holt-Winters auto-select.

Aggregation: weekly demand by product_category (or SKU if explicitly requested).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.repositories.base import Filters, OrderRepository


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _weekly_series(orders: list[dict[str, Any]], group_field: str, group_value: str) -> pd.Series:
    buckets: dict[date, int] = defaultdict(int)
    for o in orders:
        if str(o.get(group_field)) != str(group_value):
            continue
        wk = _week_start(o["order_date"])
        buckets[wk] += int(o["quantity"])
    if not buckets:
        return pd.Series(dtype=float)
    idx = sorted(buckets.keys())
    full_idx = pd.date_range(start=idx[0], end=idx[-1], freq="W-MON")
    s = pd.Series([buckets.get(d.date(), 0) for d in full_idx], index=full_idx, dtype=float)
    return s


def _moving_average_forecast(
    series: pd.Series, horizon: int, window: int = 4
) -> tuple[list[float], list[float], list[float], str]:
    if len(series) == 0:
        return [0.0] * horizon, [0.0] * horizon, [0.0] * horizon, "moving_average (no history)"
    window = min(window, max(1, len(series)))
    last_avg = float(series.tail(window).mean())
    std = float(series.tail(max(window, 4)).std(ddof=0)) if len(series) > 1 else 0.0
    z = 1.28  # ~80% PI
    forecast = [last_avg] * horizon
    lower = [max(0.0, last_avg - z * std)] * horizon
    upper = [last_avg + z * std] * horizon
    return forecast, lower, upper, f"moving_average(window={window})"


def _holt_winters_forecast(
    series: pd.Series, horizon: int, seasonal_periods: int = 4
) -> tuple[list[float], list[float], list[float], str]:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore

    use_seasonal = len(series) >= 2 * seasonal_periods
    model = ExponentialSmoothing(
        series,
        trend="add",
        seasonal="add" if use_seasonal else None,
        seasonal_periods=seasonal_periods if use_seasonal else None,
        initialization_method="estimated",
    )
    fitted = model.fit(optimized=True)
    fc = fitted.forecast(horizon)
    resid = series - fitted.fittedvalues
    sigma = float(np.std(resid.dropna(), ddof=1)) if len(resid.dropna()) > 1 else 0.0
    z = 1.28
    forecast = [max(0.0, float(v)) for v in fc.values]
    lower = [max(0.0, v - z * sigma) for v in forecast]
    upper = [v + z * sigma for v in forecast]
    method = f"holt_winters(trend=add, seasonal={'add' if use_seasonal else 'none'}, periods={seasonal_periods})"
    return forecast, lower, upper, method


def forecast_demand(
    repo: OrderRepository,
    filters: Filters,
    group_by: str,
    group_value: str,
    horizon: int = 12,
) -> dict[str, Any]:
    """Forecast weekly demand for a category (or SKU).

    Auto-selects Holt-Winters when ≥ 2× seasonal_periods of history (8 weeks),
    otherwise falls back to moving average.
    """
    if group_by not in {"product_category", "sku"}:
        raise ValueError("group_by must be 'product_category' or 'sku'")

    orders = repo.fetch_orders(filters)
    series = _weekly_series(orders, group_by, group_value)
    history = [
        {"period": d.date().isoformat(), "value": float(v)}
        for d, v in series.items()
    ]
    history_len = len(series)

    method_used: str
    if history_len >= 8:
        try:
            fc, lo, up, method_used = _holt_winters_forecast(series, horizon)
        except Exception as e:
            fc, lo, up, method_used = _moving_average_forecast(series, horizon)
            method_used += f" (HW failed: {type(e).__name__})"
    else:
        fc, lo, up, method_used = _moving_average_forecast(series, horizon)

    last_period = series.index[-1].date() if history_len else date.today()
    forecast_periods = [
        (last_period + timedelta(weeks=i + 1)).isoformat() for i in range(horizon)
    ]
    forecast = [
        {"period": p, "value": round(v, 2), "lower": round(lo[i], 2), "upper": round(up[i], 2)}
        for i, (p, v) in enumerate(zip(forecast_periods, fc))
    ]

    mean_fc = float(np.mean(fc)) if fc else 0.0
    std_fc = float(np.std(fc, ddof=0)) if len(fc) > 1 else 0.0
    inventory_recommendation = round(mean_fc + 1.65 * std_fc, 2)  # ~95% safety stock

    return {
        "group_by": group_by,
        "group_value": group_value,
        "history": history,
        "forecast": forecast,
        "method": method_used,
        "horizon_weeks": horizon,
        "history_weeks": history_len,
        "inventory_recommendation_per_week": inventory_recommendation,
        "explanation": (
            f"Used {method_used} on {history_len} weeks of history for "
            f"{group_by}='{group_value}'. Forecast {horizon} weeks ahead with 80% prediction "
            f"interval. Recommended inventory ≈ mean + 1.65·std ≈ {inventory_recommendation} "
            f"units/week (~95% service level)."
        ),
    }
