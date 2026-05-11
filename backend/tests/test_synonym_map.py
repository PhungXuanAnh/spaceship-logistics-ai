"""Unit tests for the Phase-13 synonym remap layer."""
from __future__ import annotations

import json

from app.ai.contracts import RouterResponse
from app.ai.synonym_map import normalize_router_payload


def test_remaps_metric_synonyms() -> None:
    raw = '{"intent":"query","tool":"query","query_plan":{"metric":"delayed_orders","dimension":"carrier"}}'
    out = normalize_router_payload(raw)
    assert '"metric":"delayed_count"' in out
    # Pydantic validates downstream
    resp = RouterResponse.model_validate_json(out)
    assert resp.query_plan and resp.query_plan.metric == "delayed_count"


def test_remaps_dimension_synonyms() -> None:
    raw = '{"intent":"query","tool":"query","query_plan":{"metric":"count","dimension":"order_date","granularity":"weekly"}}'
    out = normalize_router_payload(raw)
    resp = RouterResponse.model_validate_json(out)
    assert resp.query_plan and resp.query_plan.dimension == "period"
    assert resp.query_plan.granularity == "week"


def test_remaps_clarification_message_to_question() -> None:
    raw = '{"intent":"clarify","tool":"none","clarification":{"message":"Which carrier?","options":["FedEx","UPS"]}}'
    out = normalize_router_payload(raw)
    resp = RouterResponse.model_validate_json(out)
    assert resp.clarification and resp.clarification.question == "Which carrier?"
    assert resp.clarification.suggested_options == ["FedEx", "UPS"]


def test_idempotent_on_canonical_input() -> None:
    raw = '{"intent":"query","tool":"query","query_plan":{"metric":"count","dimension":"carrier"}}'
    out = normalize_router_payload(raw)
    assert out == raw  # nothing to remap
    RouterResponse.model_validate_json(out)


def test_intent_synonyms() -> None:
    raw = '{"intent":"predict","tool":"forecast","forecast_plan":{"group_by":"product_category","group_value":"Apparel"}}'
    out = normalize_router_payload(raw)
    resp = RouterResponse.model_validate_json(out)
    assert resp.intent.value == "forecast"


def test_chips_alias_still_accepted() -> None:
    """Backward-compat: legacy `chips` key should be accepted via AliasChoices."""
    raw = json.dumps({"intent": "clarify", "tool": "none", "clarification": {"question": "?", "chips": ["a", "b"]}})
    # Without normalization (alias kicks in directly via Pydantic):
    resp = RouterResponse.model_validate_json(raw)
    assert resp.clarification and resp.clarification.suggested_options == ["a", "b"]


def test_suggested_options_serialises_with_canonical_name() -> None:
    raw = '{"intent":"clarify","tool":"none","clarification":{"question":"?","chips":["a"]}}'
    resp = RouterResponse.model_validate_json(raw)
    out = resp.model_dump(by_alias=True)
    assert out["clarification"]["suggested_options"] == ["a"]
    assert "chips" not in out["clarification"]
