"""Tools: QueryTool, ForecastTool, SchemaInspectorTool.

Each tool is a thin wrapper around an analytics function + a Repository.
Tools never construct SQL strings — they pass typed Filters into the Repository.
"""
from __future__ import annotations

from typing import Any, ClassVar

from app.ai.contracts import ForecastPlan, QueryPlan
from app.ai.safety import validate_query_plan
from app.analytics import breakdowns, forecast, kpis
from app.analytics.chart_spec import derive_chart_spec
from app.repositories.base import Filters, OrderRepository


class QueryTool:
    """Used for: KPIs, breakdowns, top-N, time-series.

    Use when: 'how many', 'breakdown by carrier', 'top 5 carriers', 'orders by week'.
    Do NOT use when: 'forecast', 'predict', 'next quarter' — use ForecastTool.
    """

    name: ClassVar[str] = "query"
    description: ClassVar[str] = (
        "Query historical logistics data. Supports KPI computation, "
        "dimensional breakdowns (carrier/region/category/warehouse), top-N rankings, "
        "and time-series. Filters: date range, carrier, region, category."
    )
    _VERSION: ClassVar[str] = "v1.0"

    def __init__(self, repo: OrderRepository, tenant_client_id: str | None = None) -> None:
        self._repo = repo
        self._tenant = tenant_client_id

    def invoke(self, plan: QueryPlan) -> dict[str, Any]:
        plan = validate_query_plan(plan)
        filters = Filters(
            client_id=self._tenant,
            date_from=plan.date_from,
            date_to=plan.date_to,
            carrier=plan.carrier,
            region=plan.region,
            category=plan.category,
            warehouse=plan.warehouse,
            sku=plan.sku,
            status=plan.status,
        )

        # KPI summary (no dimension)
        if plan.dimension == "none":
            k = kpis.compute_kpis(self._repo, filters)
            value = self._kpi_value(k, plan.metric)
            chart = derive_chart_spec("kpi", None, plan.metric, 1)
            return {
                "rows": [k],
                "answer": self._kpi_answer(plan.metric, value, k),
                "chart_spec": chart,
                "row_count": 1,
            }

        # Time-series
        if plan.dimension == "period":
            rows = breakdowns.orders_over_time(self._repo, filters, plan.granularity)
            chart = derive_chart_spec("query", "period", plan.metric, len(rows))
            metric_name = (
                "delayed orders" if plan.metric == "delayed_count" else "orders"
            )
            return {
                "rows": rows,
                "answer": f"Returned {len(rows)} {plan.granularity}ly buckets of {metric_name}.",
                "chart_spec": chart,
                "row_count": len(rows),
            }

        # Breakdowns / top-N
        rows = breakdowns.breakdown_by(self._repo, filters, plan.dimension)
        if plan.top_n:
            metric = (
                plan.metric
                if plan.metric in {"delay_rate", "delivered", "delayed", "value_usd"}
                else "total"
            )
            rows = breakdowns.top_n_by(
                self._repo, filters, plan.dimension, metric=metric, n=plan.top_n
            )
            answer_metric = (
                "delay rate" if plan.metric == "delay_rate" else plan.metric.replace("_", " ")
            )
            top_label = rows[0][plan.dimension] if rows else "n/a"
            top_value = rows[0][metric] if rows else 0
            dim_plural = {
                "carrier": "carriers",
                "region": "regions",
                "product_category": "product categories",
                "warehouse": "warehouses",
                "status": "statuses",
                "destination_city": "destination cities",
                "period": "periods",
            }.get(plan.dimension, f"{plan.dimension}s")
            answer = (
                f"Top {plan.top_n} {dim_plural} by {answer_metric}. "
                f"Top: {top_label} ({top_value})."
            )
        else:
            answer = f"Breakdown by {plan.dimension}: {len(rows)} group(s)."
        chart = derive_chart_spec("query", plan.dimension, plan.metric, len(rows))
        return {"rows": rows, "answer": answer, "chart_spec": chart, "row_count": len(rows)}

    @staticmethod
    def _kpi_value(k: dict[str, Any], metric: str) -> Any:
        return {
            "count": k["total_orders"],
            "delivered_count": k["delivered_orders"],
            "delayed_count": k["delayed_orders"],
            "on_time_rate": k["on_time_delivery_rate"],
            "avg_delivery_days": k["avg_delivery_days"],
        }.get(metric, k["total_orders"])

    @staticmethod
    def _kpi_answer(metric: str, value: Any, k: dict[str, Any]) -> str:
        return {
            "count": f"Total orders: {value}.",
            "delivered_count": f"Delivered orders: {value} (of {k['total_orders']} total).",
            "delayed_count": f"Delayed orders: {value} (of {k['total_orders']} total).",
            "on_time_rate": f"On-time delivery rate: {value*100:.1f}%.",
            "avg_delivery_days": f"Average delivery time: {value} days.",
        }.get(metric, f"Total orders: {k['total_orders']}.")


class ForecastTool:
    """Used for: predicting future demand by category or SKU.

    Use when: 'forecast', 'predict', 'next 4 months', 'how much should I order'.
    Do NOT use when: 'last month', 'how many were delayed' — use QueryTool.
    """

    name: ClassVar[str] = "forecast"
    description: ClassVar[str] = (
        "Forecast weekly demand for a product_category or sku. "
        "Auto-selects Holt-Winters when history >= 8 weeks, else moving average. "
        "Returns: history, forecast values with 80% PI, methodology, inventory recommendation."
    )
    _VERSION: ClassVar[str] = "v1.0"

    def __init__(self, repo: OrderRepository, tenant_client_id: str | None = None) -> None:
        self._repo = repo
        self._tenant = tenant_client_id

    def invoke(self, plan: ForecastPlan) -> dict[str, Any]:
        filters = Filters(
            client_id=self._tenant, date_from=plan.date_from, date_to=plan.date_to
        )
        result = forecast.forecast_demand(
            self._repo, filters, plan.group_by, plan.group_value, plan.horizon_weeks
        )

        chart_spec = derive_chart_spec("forecast", "period", "value", len(result["forecast"]))

        # Combine history + forecast into a single chart-friendly series
        series_rows = [
            {"period": h["period"], "actual": h["value"], "forecast": None, "lower": None, "upper": None}
            for h in result["history"]
        ] + [
            {"period": f["period"], "actual": None, "forecast": f["value"], "lower": f["lower"], "upper": f["upper"]}
            for f in result["forecast"]
        ]

        answer = (
            f"Forecast for {plan.group_by}='{plan.group_value}' over the next "
            f"{plan.horizon_weeks} weeks. {result['explanation']}"
        )
        return {
            "rows": series_rows,
            "answer": answer,
            "chart_spec": chart_spec,
            "row_count": len(series_rows),
            "method": result["method"],
            "history_weeks": result["history_weeks"],
            "inventory_recommendation_per_week": result["inventory_recommendation_per_week"],
        }


class SchemaInspectorTool:
    """Used for: listing valid carriers/categories/regions when the LLM needs to validate
    a value the user mentioned.

    Use when: user mentions a carrier/category name we can't validate.
    Do NOT use when: question is already concrete and the value is a known one.
    """

    name: ClassVar[str] = "schema_inspect"
    description: ClassVar[str] = (
        "Return distinct values for low-cardinality columns "
        "(carrier, region, product_category, warehouse, status)."
    )
    _VERSION: ClassVar[str] = "v1.0"

    def __init__(self, repo: OrderRepository) -> None:
        self._repo = repo

    def invoke(self, column: str = "carrier") -> dict[str, Any]:
        values = self._repo.distinct_values(column)
        d_from, d_to = self._repo.date_range()
        return {
            "column": column,
            "values": values,
            "date_range": [d_from.isoformat() if d_from else None, d_to.isoformat() if d_to else None],
        }
