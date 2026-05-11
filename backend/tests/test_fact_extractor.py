"""Unit tests for the fact_extractor — the belt-and-suspenders
post-processor that re-parses the user's prompt and backfills any
query_plan field the LLM dropped."""
from __future__ import annotations

from datetime import date

import pytest

from app.ai.fact_extractor import (
    ExtractedFacts,
    backfill_plan,
    extract_facts,
    extract_re_chips,
    unwrap_re_prompt,
)


class TestUnwrapRePrompt:
    def test_plain_prompt_passthrough(self):
        q = "Top 5 carriers by delay rate"
        assert unwrap_re_prompt(q) == q

    def test_single_re_layer(self):
        q = 'Re: "Top 5 SKUs by delivered volume in Vietnam in October" — use EU.'
        assert unwrap_re_prompt(q) == "Top 5 SKUs by delivered volume in Vietnam in October"

    def test_multi_chip_single_layer(self):
        q = 'Re: "Top 5 SKUs in Vietnam in October" — use EU; product_category.'
        assert unwrap_re_prompt(q) == "Top 5 SKUs in Vietnam in October"

    def test_legacy_nested_layers(self):
        # If the FE ever regresses to stacking, we still peel back.
        q = 'Re: "Re: "Top 5 SKUs in Vietnam" — use EU." — use product_category.'
        assert unwrap_re_prompt(q) == "Top 5 SKUs in Vietnam"

    def test_strips_whitespace(self):
        q = '   Re: "Hello" — use X.   '
        assert unwrap_re_prompt(q) == "Hello"

    def test_no_infinite_loop_on_malformed(self):
        # 11 nested layers (1 over the safety limit) — should not hang.
        q = '"x"' * 11
        result = unwrap_re_prompt(q)
        assert isinstance(result, str)


class TestExtractReChips:
    def test_plain_prompt_no_chips(self):
        assert extract_re_chips("Top 5 carriers") == []

    def test_single_chip(self):
        q = 'Re: "Top 5 SKUs in Vietnam in October" — use EU.'
        assert extract_re_chips(q) == ["EU"]

    def test_multiple_chips_semicolon(self):
        q = 'Re: "Top 5 SKUs in Vietnam in October" — use EU; product_category.'
        assert extract_re_chips(q) == ["EU", "product_category"]

    def test_nested_layers_oldest_first(self):
        q = 'Re: "Re: "Top 5 SKUs in Vietnam" — use EU." — use product_category.'
        assert extract_re_chips(q) == ["EU", "product_category"]


class TestExtractFacts:
    def test_month_name_no_year_defaults_to_passed_year(self):
        facts = extract_facts("orders in October", default_year=2025)
        assert facts.date_from == date(2025, 10, 1)
        assert facts.date_to == date(2025, 10, 31)

    def test_month_name_with_explicit_year(self):
        facts = extract_facts("delivered count for July 2024")
        assert facts.date_from == date(2024, 7, 1)
        assert facts.date_to == date(2024, 7, 31)

    def test_month_abbrev(self):
        facts = extract_facts("orders in Nov", default_year=2026)
        assert facts.date_from == date(2026, 11, 1)
        assert facts.date_to == date(2026, 11, 30)

    def test_december_end_of_year(self):
        facts = extract_facts("orders in December 2025")
        assert facts.date_from == date(2025, 12, 1)
        assert facts.date_to == date(2025, 12, 31)

    def test_relative_time_wins_over_month(self):
        # "last 30 days" is more specific than a stray "October" — keyword
        # router's _parse_time_window should win.
        facts = extract_facts("delivered last 30 days in October")
        # Relative-time returns a non-None range that ISN'T Oct 1-31.
        assert facts.date_from is not None
        assert facts.date_to is not None
        assert (facts.date_to - facts.date_from).days == 30

    def test_detects_region(self):
        facts = extract_facts("delivered orders in EU")
        assert "EU" in facts.regions

    def test_detects_carrier(self):
        facts = extract_facts("DHL delay rate this quarter")
        assert "DHL" in facts.carriers

    def test_detects_category(self):
        facts = extract_facts("forecast for CRAYON next 4 weeks")
        assert "CRAYON" in facts.categories

    def test_detects_warehouse(self):
        facts = extract_facts("shipments from AMS-FC1 last week")
        assert "AMS-FC1" in facts.warehouses

    def test_detects_status(self):
        facts = extract_facts("count of delivered orders")
        assert "delivered" in facts.statuses

    def test_re_prompt_extracts_from_inner_original_and_chips(self):
        # The whole point of Fix 3: even when the LLM is given a Re: prompt
        # with chip values, the backend must still see "October" and the
        # chip-selected "EU" so the final plan has both.
        q = 'Re: "Top 5 SKUs by delivered volume in Vietnam in October" — use EU; product_category.'
        facts = extract_facts(q, default_year=2025)
        assert facts.date_from == date(2025, 10, 1)
        assert facts.date_to == date(2025, 10, 31)
        # Vietnam isn't a known region, but the chip "EU" is, so we surface it.
        # "product_category" isn't a filter value (it's a dimension keyword),
        # so the LLM keeps responsibility for that one.
        assert "EU" in facts.regions


class TestBackfillPlan:
    def _plan(self, **overrides) -> dict:
        base = {
            "metric": "delivered_count",
            "dimension": "product_category",
            "granularity": "month",
            "top_n": 5,
            "date_from": None,
            "date_to": None,
            "carrier": [],
            "region": [],
            "category": [],
            "warehouse": [],
            "sku": [],
            "status": [],
        }
        base.update(overrides)
        return base

    def test_fills_empty_dates(self):
        facts = ExtractedFacts(
            date_from=date(2025, 10, 1), date_to=date(2025, 10, 31)
        )
        plan, filled = backfill_plan(self._plan(), facts)
        assert plan["date_from"] == "2025-10-01"
        assert plan["date_to"] == "2025-10-31"
        assert "date_from" in filled and "date_to" in filled

    def test_overrides_existing_dates_when_facts_resolved(self):
        # Session 36.1: dates are aggressive-override (parity between v1/v2).
        # When facts has resolved relative-time dates, facts always wins.
        facts = ExtractedFacts(
            date_from=date(2025, 10, 1), date_to=date(2025, 10, 31)
        )
        plan, filled = backfill_plan(
            self._plan(date_from="2024-01-01", date_to="2024-01-31"), facts
        )
        assert plan["date_from"] == "2025-10-01"
        assert plan["date_to"] == "2025-10-31"
        assert "date_from" in filled

    def test_fills_empty_region_list(self):
        facts = ExtractedFacts(regions=["EU"])
        plan, filled = backfill_plan(self._plan(), facts)
        assert plan["region"] == ["EU"]
        assert "region" in filled

    def test_does_not_overwrite_existing_region(self):
        # LLM picked UK from a chip — we don't clobber it with EU from facts.
        facts = ExtractedFacts(regions=["EU"])
        plan, filled = backfill_plan(self._plan(region=["UK"]), facts)
        assert plan["region"] == ["UK"]
        assert "region" not in filled

    def test_fills_empty_carrier_and_category(self):
        facts = ExtractedFacts(carriers=["DHL"], categories=["CRAYON"])
        plan, filled = backfill_plan(self._plan(), facts)
        assert plan["carrier"] == ["DHL"]
        assert plan["category"] == ["CRAYON"]
        assert "carrier" in filled and "category" in filled

    def test_no_facts_no_changes(self):
        plan, filled = backfill_plan(self._plan(), ExtractedFacts())
        assert filled == []

    def test_partial_overlap(self):
        # LLM filled region but not date — only date gets backfilled.
        facts = ExtractedFacts(
            date_from=date(2025, 10, 1),
            date_to=date(2025, 10, 31),
            regions=["EU"],
        )
        plan, filled = backfill_plan(self._plan(region=["UK"]), facts)
        assert plan["region"] == ["UK"]
        assert plan["date_from"] == "2025-10-01"
        assert filled == ["date_from", "date_to"]


class TestEndToEndScenarios:
    """The original bugs that drove Fix 3, as integration-level tests
    over (extract_facts → backfill_plan). No LLM involved."""

    def test_vietnam_october_eu_followup_recovers_october(self):
        # User asked Vietnam+October, then clicked EU. LLM rebuilds the plan
        # with region=EU but drops the October date range. The fact extractor
        # finds October in the inner original and the backfiller fills it.
        q = 'Re: "Top 5 SKUs by delivered volume in Vietnam in October" — use EU; product_category.'
        facts = extract_facts(q, default_year=2025)
        # LLM correctly set region=EU but dropped the date.
        llm_plan = {
            "metric": "delivered_count",
            "dimension": "product_category",
            "granularity": "month",
            "top_n": 5,
            "date_from": None,
            "date_to": None,
            "carrier": [],
            "region": ["EU"],
            "category": [],
            "warehouse": [],
            "sku": [],
            "status": [],
        }
        plan, filled = backfill_plan(llm_plan, facts)
        assert plan["region"] == ["EU"]  # preserved
        assert plan["date_from"] == "2025-10-01"
        assert plan["date_to"] == "2025-10-31"
        assert "date_from" in filled

    def test_vietnam_october_eu_followup_recovers_BOTH_date_and_region(self):
        # Harder case: LLM dropped BOTH region (didn't merge the chip) AND
        # date (didn't preserve "October"). Backfill recovers both from
        # (a) the inner original prompt for October, and (b) the chip suffix
        # for EU.
        q = 'Re: "Top 5 SKUs by delivered volume in Vietnam in October" — use EU; product_category.'
        facts = extract_facts(q, default_year=2025)
        llm_plan = {
            "metric": "delivered_count",
            "dimension": "product_category",
            "granularity": "month",
            "top_n": 5,
            "date_from": None,
            "date_to": None,
            "carrier": [],
            "region": [],  # ← LLM dropped EU
            "category": [],
            "warehouse": [],
            "sku": [],
            "status": [],
        }
        plan, filled = backfill_plan(llm_plan, facts)
        assert plan["region"] == ["EU"]
        assert plan["date_from"] == "2025-10-01"
        assert plan["date_to"] == "2025-10-31"
        assert "region" in filled and "date_from" in filled

    def test_dhl_last_week_followup_recovers_carrier(self):
        # User asked "DHL delays last week", then clicked a chip. LLM rewrites
        # and drops carrier. Backfill finds DHL in the inner original.
        q = 'Re: "DHL delays last week" — use by region.'
        facts = extract_facts(q)
        llm_plan = {
            "metric": "delay_rate",
            "dimension": "region",
            "granularity": "week",
            "top_n": None,
            "date_from": None,  # LLM also dropped the date
            "date_to": None,
            "carrier": [],  # ← LLM dropped DHL
            "region": [],
            "category": [],
            "warehouse": [],
            "sku": [],
            "status": [],
        }
        plan, filled = backfill_plan(llm_plan, facts)
        assert plan["carrier"] == ["DHL"]
        assert "carrier" in filled
        # last week → ~7-day range
        assert plan["date_from"] is not None
        assert plan["date_to"] is not None
