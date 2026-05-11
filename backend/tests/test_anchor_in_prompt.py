"""Session 36 — anchor in system prompt + defensive out-of-range backfill.

Verifies:
1. ClaudeRouter and GeminiNativeRouter both inject DATASET_DATE_RANGE +
   TODAY into the system prompt when schema_hint includes date_range.
2. backfill_plan overrides LLM-supplied dates that fall fully outside
   the dataset range when the prompt resolves to an in-range relative
   window (the Gemini "last 3 months" → 2025-04-15..2025-07-15 bug).
3. backfill_plan does NOT overwrite LLM dates that are inside / overlap
   the dataset range.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.fact_extractor import ExtractedFacts, backfill_plan
from app.ai.providers.claude import ClaudeRouter
from app.ai.providers.gemini_native import GeminiNativeRouter


# ---------------------------------------------------------------------------
# 1. System prompt injection
# ---------------------------------------------------------------------------

SCHEMA_HINT = {
    "carriers": ["DHL", "USPS"],
    "categories": ["BOOK"],
    "regions": ["EU"],
    "date_range": ["2025-01-01", "2025-12-30"],
}


def _capture_claude_system() -> str:
    """Run ClaudeRouter.route with a stubbed _call and return the system text."""
    captured: dict = {}

    async def fake_call(self, system, messages):
        captured["system"] = system
        # Return a minimal valid RouterResponse so route() returns cleanly.
        return '{"intent":"refuse","tool":"none","clarification":null,"refusal_reason":"x","query_plan":null,"forecast_plan":null,"inspect_column":null}'

    router = ClaudeRouter(api_key="k", model="m", base_url="http://x")
    with patch.object(ClaudeRouter, "_call", fake_call):
        asyncio.run(router.route("hi", schema_hint=SCHEMA_HINT))
    return captured["system"]


def _capture_gemini_system() -> str:
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {
                "candidates": [{
                    "content": {"parts": [{
                        "functionCall": {
                            "name": "refuse",
                            "args": {"refusal_reason": "x"},
                        }
                    }]}
                }]
            }

    async def fake_post(url, json):  # noqa: A002
        captured["system"] = json["system_instruction"]["parts"][0]["text"]
        return FakeResponse()

    router = GeminiNativeRouter(api_key="k", model="m")
    with patch("app.ai.providers.gemini_native.httpx.AsyncClient") as mock_cli:
        instance = mock_cli.return_value.__aenter__.return_value
        instance.post = fake_post
        asyncio.run(router.route("hi", schema_hint=SCHEMA_HINT))
    return captured["system"]


class TestClaudeSystemPromptHasAnchor:
    def test_claude_system_contains_dataset_date_range(self):
        sys = _capture_claude_system()
        assert "DATASET_DATE_RANGE: 2025-01-01 to 2025-12-30" in sys

    def test_claude_system_contains_today_anchor(self):
        sys = _capture_claude_system()
        assert "TODAY" in sys and "2025-12-30" in sys

    def test_claude_system_no_anchor_when_no_date_range(self):
        captured: dict = {}

        async def fake_call(self, system, messages):
            captured["system"] = system
            return '{"intent":"refuse","tool":"none","clarification":null,"refusal_reason":"x","query_plan":null,"forecast_plan":null,"inspect_column":null}'

        router = ClaudeRouter(api_key="k", model="m", base_url="http://x")
        with patch.object(ClaudeRouter, "_call", fake_call):
            asyncio.run(router.route("hi", schema_hint={"carriers": ["DHL"]}))
        assert "DATASET_DATE_RANGE" not in captured["system"]


class TestGeminiSystemPromptHasAnchor:
    def test_gemini_system_contains_dataset_date_range(self):
        sys = _capture_gemini_system()
        assert "DATASET_DATE_RANGE: 2025-01-01 to 2025-12-30" in sys

    def test_gemini_system_contains_today_anchor(self):
        sys = _capture_gemini_system()
        assert "TODAY" in sys and "2025-12-30" in sys


# ---------------------------------------------------------------------------
# 2. Defensive out-of-range backfill
# ---------------------------------------------------------------------------

DATASET_RANGE = (date(2025, 9, 1), date(2025, 12, 30))


class TestOutOfRangeBackfillOverride:
    """Canonical override: when facts has resolved relative-time dates,
    they ALWAYS win over the LLM's dates — guaranteeing v1/v2 parity.
    Free-form ranges (facts.date_from is None) are passed through."""

    def test_overrides_when_llm_dates_fully_before_dataset(self):
        """Gemini's 2025-04-15..2025-07-15 falls fully before dataset (Sep–Dec)."""
        plan = {"date_from": "2025-04-15", "date_to": "2025-07-15", "metric": "delayed_count"}
        facts = ExtractedFacts(date_from=date(2025, 9, 30), date_to=date(2025, 12, 30))
        out, filled = backfill_plan(plan, facts, dataset_range=DATASET_RANGE)
        assert out["date_from"] == "2025-09-30"
        assert out["date_to"] == "2025-12-30"
        assert "date_from" in filled and "date_to" in filled

    def test_overrides_when_llm_dates_fully_after_dataset(self):
        """Wall-clock-anchored "last 3 months" run on 2026-05-11 → Feb–May 2026."""
        plan = {"date_from": "2026-02-11", "date_to": "2026-05-11", "metric": "delayed_count"}
        facts = ExtractedFacts(date_from=date(2025, 9, 30), date_to=date(2025, 12, 30))
        out, filled = backfill_plan(plan, facts, dataset_range=DATASET_RANGE)
        assert out["date_from"] == "2025-09-30"
        assert out["date_to"] == "2025-12-30"

    def test_overrides_when_llm_dates_overlap_dataset(self):
        """Even when LLM's window touches dataset, facts wins for parity."""
        plan = {"date_from": "2025-08-15", "date_to": "2025-10-15", "metric": "delayed_count"}
        facts = ExtractedFacts(date_from=date(2025, 9, 30), date_to=date(2025, 12, 30))
        out, filled = backfill_plan(plan, facts, dataset_range=DATASET_RANGE)
        assert out["date_from"] == "2025-09-30"
        assert out["date_to"] == "2025-12-30"
        assert "date_from" in filled and "date_to" in filled

    def test_overrides_when_llm_dates_fully_inside_dataset(self):
        """v2 case: gemini-native picks Sep 30, facts says Oct 1 — facts wins."""
        plan = {"date_from": "2025-09-30", "date_to": "2025-12-30", "metric": "delayed_count"}
        facts = ExtractedFacts(date_from=date(2025, 10, 1), date_to=date(2025, 12, 30))
        out, filled = backfill_plan(plan, facts, dataset_range=DATASET_RANGE)
        assert out["date_from"] == "2025-10-01"
        assert out["date_to"] == "2025-12-30"
        assert "date_from" in filled

    def test_no_override_when_llm_dates_match_facts(self):
        """No-op when LLM already matches the canonical resolution."""
        plan = {"date_from": "2025-10-01", "date_to": "2025-12-30", "metric": "delayed_count"}
        facts = ExtractedFacts(date_from=date(2025, 10, 1), date_to=date(2025, 12, 30))
        out, filled = backfill_plan(plan, facts, dataset_range=DATASET_RANGE)
        assert out["date_from"] == "2025-10-01"
        assert out["date_to"] == "2025-12-30"
        assert "date_from" not in filled
        assert "date_to" not in filled

    def test_no_override_when_facts_have_no_relative_date(self):
        """Free-form ranges (facts has None) → LLM dates passed through."""
        plan = {"date_from": "2026-02-11", "date_to": "2026-05-11", "metric": "delayed_count"}
        facts = ExtractedFacts(date_from=None, date_to=None)
        out, filled = backfill_plan(plan, facts, dataset_range=DATASET_RANGE)
        assert out["date_from"] == "2026-02-11"
        assert "date_from" not in filled

    def test_handles_malformed_date_strings_gracefully(self):
        """Override succeeds even when LLM returned garbage strings."""
        plan = {"date_from": "not-a-date", "date_to": "also-not", "metric": "delayed_count"}
        facts = ExtractedFacts(date_from=date(2025, 10, 1), date_to=date(2025, 12, 30))
        out, filled = backfill_plan(plan, facts, dataset_range=DATASET_RANGE)
        assert out["date_from"] == "2025-10-01"
        assert out["date_to"] == "2025-12-30"
