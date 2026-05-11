"""Unit tests for the Phase-14 GeminiNativeRouter schema adapter."""
from __future__ import annotations

from app.ai.contracts import ForecastPlan, QueryPlan
from app.ai.providers.gemini_native import (
    GeminiNativeRouter,
    _build_function_declarations,
    _to_gemini_schema,
)


def test_strips_anyOf_optional() -> None:
    schema = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert _to_gemini_schema(schema) == {"type": "string"}


def test_strips_defs_ref_title_default() -> None:
    schema = {
        "type": "object",
        "title": "Foo",
        "default": {},
        "$defs": {"Bar": {"type": "integer"}},
        "properties": {"x": {"type": "integer", "default": 0}},
    }
    out = _to_gemini_schema(schema)
    assert "title" not in out
    assert "default" not in out
    assert "$defs" not in out
    assert out["properties"]["x"] == {"type": "integer"}


def test_strips_unsupported_format() -> None:
    schema = {"type": "string", "format": "uuid"}
    assert _to_gemini_schema(schema) == {"type": "string"}


def test_keeps_supported_format() -> None:
    schema = {"type": "string", "format": "date"}
    assert _to_gemini_schema(schema) == {"type": "string", "format": "date"}


def test_recurses_into_items_and_properties() -> None:
    schema = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "null"}]}}
        },
    }
    out = _to_gemini_schema(schema)
    assert out["properties"]["tags"]["items"] == {"type": "string"}


def test_query_plan_schema_round_trips() -> None:
    out = _to_gemini_schema(QueryPlan.model_json_schema())
    assert out["type"] == "object"
    assert "metric" in out["properties"]
    assert out["properties"]["metric"]["enum"][0] == "count"
    # Ensure no anyOf / $defs leak through
    s = str(out)
    assert "anyOf" not in s
    assert "$defs" not in s
    assert "$ref" not in s


def test_forecast_plan_schema_round_trips() -> None:
    out = _to_gemini_schema(ForecastPlan.model_json_schema())
    assert "group_by" in out["properties"]
    assert "horizon_weeks" in out["properties"]


def test_function_declarations_includes_all_five_tools() -> None:
    fns = _build_function_declarations()
    names = [f["name"] for f in fns]
    assert names == ["query", "forecast", "schema_inspect", "clarify", "refuse"]


def test_functioncall_to_router_response_query() -> None:
    resp = GeminiNativeRouter._functioncall_to_router_response(
        "query", {"metric": "delayed_count", "dimension": "carrier", "top_n": 3}
    )
    assert resp.intent.value == "query"
    assert resp.query_plan and resp.query_plan.metric == "delayed_count"
    assert resp.query_plan.top_n == 3


def test_functioncall_to_router_response_clarify() -> None:
    resp = GeminiNativeRouter._functioncall_to_router_response(
        "clarify", {"question": "Which carrier?", "suggested_options": ["A", "B", "C"]}
    )
    assert resp.intent.value == "clarify"
    assert resp.clarification and resp.clarification.suggested_options == ["A", "B", "C"]


def test_functioncall_to_router_response_refuse() -> None:
    resp = GeminiNativeRouter._functioncall_to_router_response(
        "refuse", {"refusal_reason": "off-topic"}
    )
    assert resp.intent.value == "refuse"
    assert resp.refusal_reason == "off-topic"
