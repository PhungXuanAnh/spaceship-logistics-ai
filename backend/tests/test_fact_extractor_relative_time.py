"""Comprehensive tests for relative-time + top_n + broader silent-drop
scenarios that the v1 LLM is known to drop on Re: prompts.

These complement test_fact_extractor.py with the Session 35 expansion.
"""
from datetime import date

from app.ai.fact_extractor import (
    ExtractedFacts,
    _parse_relative_time,
    _parse_top_n,
    backfill_plan,
    extract_facts,
)

# Anchor used for all relative-time tests = the dataset's max date for
# the demo full-2025 dataset.
ANCHOR = date(2025, 12, 31)


# ---------------------------------------------------------------------------
# _parse_relative_time
# ---------------------------------------------------------------------------
class TestRelativeTimeQuarters:
    def test_this_quarter_at_year_end(self):
        df, dt = _parse_relative_time("highest delay this quarter", ANCHOR)
        assert df == date(2025, 10, 1) and dt == date(2025, 12, 31)

    def test_this_quarter_in_q2(self):
        df, dt = _parse_relative_time("delay this quarter", date(2025, 5, 15))
        assert df == date(2025, 4, 1) and dt == date(2025, 6, 30)

    def test_last_quarter_at_year_end(self):
        df, dt = _parse_relative_time("delay last quarter", ANCHOR)
        assert df == date(2025, 7, 1) and dt == date(2025, 9, 30)

    def test_last_quarter_wraps_to_prev_year(self):
        df, dt = _parse_relative_time("delay last quarter", date(2025, 2, 1))
        assert df == date(2024, 10, 1) and dt == date(2024, 12, 31)

    def test_qtd_alias(self):
        df, dt = _parse_relative_time("QTD performance", ANCHOR)
        assert df == date(2025, 10, 1) and dt == date(2025, 12, 31)

    def test_q4_explicit(self):
        df, dt = _parse_relative_time("delay rate in Q4", ANCHOR)
        assert df == date(2025, 10, 1) and dt == date(2025, 12, 31)

    def test_q4_with_year(self):
        df, dt = _parse_relative_time("delay rate in Q4 2024", ANCHOR)
        assert df == date(2024, 10, 1) and dt == date(2024, 12, 31)

    def test_q1_uses_anchor_year(self):
        df, dt = _parse_relative_time("Q1 numbers", ANCHOR)
        assert df == date(2025, 1, 1) and dt == date(2025, 3, 31)

    def test_q2_full_range(self):
        df, dt = _parse_relative_time("Q2 results", ANCHOR)
        assert df == date(2025, 4, 1) and dt == date(2025, 6, 30)

    def test_q3_full_range(self):
        df, dt = _parse_relative_time("Q3 results", ANCHOR)
        assert df == date(2025, 7, 1) and dt == date(2025, 9, 30)


class TestRelativeTimeYears:
    def test_this_year(self):
        df, dt = _parse_relative_time("orders this year", ANCHOR)
        assert df == date(2025, 1, 1) and dt == date(2025, 12, 31)

    def test_ytd_alias(self):
        df, dt = _parse_relative_time("YTD revenue", ANCHOR)
        assert df == date(2025, 1, 1) and dt == date(2025, 12, 31)

    def test_year_to_date_full_words(self):
        df, dt = _parse_relative_time("year to date totals", ANCHOR)
        assert df == date(2025, 1, 1) and dt == date(2025, 12, 31)

    def test_last_year(self):
        df, dt = _parse_relative_time("orders last year", ANCHOR)
        assert df == date(2024, 1, 1) and dt == date(2024, 12, 31)


class TestRelativeTimeMonths:
    def test_this_month(self):
        df, dt = _parse_relative_time("orders this month", ANCHOR)
        assert df == date(2025, 12, 1) and dt == date(2025, 12, 31)

    def test_mtd_alias(self):
        df, dt = _parse_relative_time("MTD KPI", ANCHOR)
        assert df == date(2025, 12, 1) and dt == date(2025, 12, 31)

    def test_last_month_at_year_end(self):
        df, dt = _parse_relative_time("orders last month", ANCHOR)
        assert df == date(2025, 11, 1) and dt == date(2025, 11, 30)

    def test_last_month_wraps_to_prev_december(self):
        df, dt = _parse_relative_time("orders last month", date(2025, 1, 15))
        assert df == date(2024, 12, 1) and dt == date(2024, 12, 31)


class TestRelativeTimeWeeks:
    def test_this_week(self):
        # Anchor = 2025-12-31 (Wednesday); Monday of that week = 2025-12-29
        df, dt = _parse_relative_time("this week", ANCHOR)
        assert df == date(2025, 12, 29) and dt == ANCHOR

    def test_last_week(self):
        # Previous Mon-Sun = 2025-12-22..2025-12-28
        df, dt = _parse_relative_time("last week", ANCHOR)
        assert df == date(2025, 12, 22) and dt == date(2025, 12, 28)


class TestRelativeTimeLastNUnits:
    def test_last_30_days(self):
        df, dt = _parse_relative_time("last 30 days", ANCHOR)
        assert df == date(2025, 12, 1) and dt == ANCHOR

    def test_past_7_days(self):
        df, dt = _parse_relative_time("past 7 days", ANCHOR)
        assert df == date(2025, 12, 24) and dt == ANCHOR

    def test_last_3_months(self):
        df, dt = _parse_relative_time("last 3 months", ANCHOR)
        # Interpretation C: current month + previous 2 complete months.
        # Anchor=Dec 31 → Oct, Nov, Dec → start = Oct 1.
        assert df == date(2025, 10, 1) and dt == ANCHOR

    def test_last_2_quarters(self):
        df, dt = _parse_relative_time("past 2 quarters", ANCHOR)
        # Dec is Q4. Q4 - 2 = Q2. Start of Q2 = Apr 1.
        assert df == date(2025, 4, 1) and dt == ANCHOR

    def test_last_1_year(self):
        df, dt = _parse_relative_time("last 1 year", ANCHOR)
        assert df == date(2024, 12, 31) and dt == ANCHOR


class TestRelativeTimeTodayYesterday:
    def test_today(self):
        df, dt = _parse_relative_time("orders today", ANCHOR)
        assert df == ANCHOR and dt == ANCHOR

    def test_yesterday(self):
        df, dt = _parse_relative_time("orders yesterday", ANCHOR)
        assert df == date(2025, 12, 30) and dt == date(2025, 12, 30)


class TestRelativeTimeNoMatch:
    def test_no_time_phrase(self):
        df, dt = _parse_relative_time("orders by carrier", ANCHOR)
        assert df is None and dt is None

    def test_only_month_name_doesnt_match_relative(self):
        # Month names are handled by _parse_month_window, not this function
        df, dt = _parse_relative_time("orders in October", ANCHOR)
        assert df is None and dt is None


# ---------------------------------------------------------------------------
# _parse_top_n
# ---------------------------------------------------------------------------
class TestParseTopN:
    def test_top_5(self):
        assert _parse_top_n("Top 5 carriers") == 5

    def test_top_10(self):
        assert _parse_top_n("top 10 carriers") == 10

    def test_top_dash_10(self):
        assert _parse_top_n("top-10") == 10

    def test_top_glued_15(self):
        assert _parse_top_n("top15 carriers") == 15

    def test_n_worst(self):
        assert _parse_top_n("3 worst carriers") == 3

    def test_n_highest(self):
        assert _parse_top_n("7 highest delay rates") == 7

    def test_n_most(self):
        assert _parse_top_n("5 most delayed orders") == 5

    def test_no_number(self):
        assert _parse_top_n("which carrier is best") is None

    def test_clamps_to_50(self):
        assert _parse_top_n("top 99 carriers") == 50

    def test_clamps_to_1_minimum(self):
        assert _parse_top_n("top 0 carriers") == 1


# ---------------------------------------------------------------------------
# extract_facts with anchor
# ---------------------------------------------------------------------------
class TestExtractFactsAnchorAware:
    def test_this_quarter_uses_anchor(self):
        facts = extract_facts(
            "highest delay rate this quarter", anchor=ANCHOR
        )
        assert facts.date_from == date(2025, 10, 1)
        assert facts.date_to == date(2025, 12, 31)

    def test_this_year_uses_anchor_not_today(self):
        # The bug we're fixing: keyword router used wall-clock today, so
        # "this year" against a 2025 dataset queried in 2026 returned 0 rows.
        facts = extract_facts("orders this year", anchor=ANCHOR)
        assert facts.date_from == date(2025, 1, 1)
        assert facts.date_to == date(2025, 12, 31)

    def test_last_quarter_with_dataset_anchor(self):
        facts = extract_facts("orders last quarter", anchor=ANCHOR)
        assert facts.date_from == date(2025, 7, 1)
        assert facts.date_to == date(2025, 9, 30)

    def test_relative_time_wins_over_month_name(self):
        # Both "this quarter" AND "October" mentioned — relative wins
        facts = extract_facts(
            "highest delay this quarter not October", anchor=ANCHOR
        )
        # this quarter at Dec 31 2025 = Q4 = Oct 1..Dec 31
        assert facts.date_from == date(2025, 10, 1)
        assert facts.date_to == date(2025, 12, 31)

    def test_top_n_extracted(self):
        facts = extract_facts("top 10 carriers by delay rate", anchor=ANCHOR)
        assert facts.top_n == 10


# ---------------------------------------------------------------------------
# backfill_plan with top_n
# ---------------------------------------------------------------------------
class TestBackfillTopN:
    def test_fills_top_n_when_none(self):
        facts = ExtractedFacts(top_n=10)
        out, filled = backfill_plan({"top_n": None}, facts)
        assert out["top_n"] == 10
        assert "top_n" in filled

    def test_overrides_when_llm_picked_different(self):
        # User said "top 10", LLM returned 5 → override
        facts = ExtractedFacts(top_n=10)
        out, filled = backfill_plan({"top_n": 5}, facts)
        assert out["top_n"] == 10
        assert "top_n" in filled

    def test_no_change_when_llm_matches_user(self):
        facts = ExtractedFacts(top_n=10)
        out, filled = backfill_plan({"top_n": 10}, facts)
        assert out["top_n"] == 10
        assert "top_n" not in filled

    def test_no_change_when_no_facts_top_n(self):
        # User didn't say a number; LLM's value stands
        facts = ExtractedFacts(top_n=None)
        out, filled = backfill_plan({"top_n": 5}, facts)
        assert out["top_n"] == 5
        assert "top_n" not in filled


# ---------------------------------------------------------------------------
# End-to-end silent-drop scenarios (the scenarios the user has actually hit)
# ---------------------------------------------------------------------------
class TestSilentDropScenarios:
    """Each test simulates a known v1 silent-drop bug and asserts the
    backfill recovers the dropped fact."""

    def test_this_quarter_dropped_recovers(self):
        # Bug: claude returned date_from/date_to=null when user said "this quarter"
        question = "Which carrier has the highest delay rate this quarter?"
        facts = extract_facts(question, anchor=ANCHOR)
        plan = {
            "metric": "delay_rate",
            "dimension": "carrier",
            "date_from": None,
            "date_to": None,
        }
        out, filled = backfill_plan(plan, facts)
        assert out["date_from"] == "2025-10-01"
        assert out["date_to"] == "2025-12-31"
        assert "date_from" in filled and "date_to" in filled

    def test_last_quarter_dropped_recovers(self):
        question = "Top 5 carriers by delivered volume last quarter"
        facts = extract_facts(question, anchor=ANCHOR)
        plan = {"metric": "delivered_count", "date_from": None, "date_to": None}
        out, _ = backfill_plan(plan, facts)
        assert out["date_from"] == "2025-07-01"
        assert out["date_to"] == "2025-09-30"

    def test_this_year_dropped_recovers(self):
        question = "Total orders this year"
        facts = extract_facts(question, anchor=ANCHOR)
        plan = {"date_from": None, "date_to": None}
        out, _ = backfill_plan(plan, facts)
        assert out["date_from"] == "2025-01-01"
        assert out["date_to"] == "2025-12-31"

    def test_last_30_days_dropped_recovers(self):
        question = "Show orders in the last 30 days"
        facts = extract_facts(question, anchor=ANCHOR)
        plan = {"date_from": None, "date_to": None}
        out, _ = backfill_plan(plan, facts)
        assert out["date_from"] == "2025-12-01"
        assert out["date_to"] == "2025-12-31"

    def test_top_10_dropped_to_5_recovers(self):
        # Bug from Session 20: keyword router hard-coded top_n=5 even when
        # user said "top 10". Same pattern can happen with claude.
        question = "Top 10 worst carriers by delay rate this quarter"
        facts = extract_facts(question, anchor=ANCHOR)
        plan = {"top_n": 5, "date_from": None, "date_to": None}
        out, filled = backfill_plan(plan, facts)
        assert out["top_n"] == 10
        assert out["date_from"] == "2025-10-01"
        assert "top_n" in filled

    def test_re_prompt_with_relative_time_in_original(self):
        # The original Vietnam/October bug, but with "this quarter" instead
        # of "October" as the dropped time facet.
        question = (
            'Re: "Top 5 SKUs by delivered volume in Vietnam this quarter" '
            "— use EU; product_category."
        )
        facts = extract_facts(question, anchor=ANCHOR)
        # this quarter for anchor=2025-12-31 → Q4 = Oct 1..Dec 31
        assert facts.date_from == date(2025, 10, 1)
        assert facts.date_to == date(2025, 12, 31)
        # Region from chip
        assert "EU" in facts.regions

        plan = {"region": [], "date_from": None, "date_to": None, "dimension": "product_category"}
        out, filled = backfill_plan(plan, facts)
        assert out["region"] == ["EU"]
        assert out["date_from"] == "2025-10-01"
        assert out["date_to"] == "2025-12-31"

    def test_overrides_llm_dates_when_facts_resolved(self):
        # Session 36.1: aggressive override for v1/v2 parity. When the prompt
        # contains a parseable relative-time phrase, facts always win over
        # whatever the LLM picked. "this quarter" → Q4 = Oct 1..Dec 31.
        question = "this quarter delay rate"
        facts = extract_facts(question, anchor=ANCHOR)
        plan = {"date_from": "2025-11-01", "date_to": "2025-11-15"}
        out, filled = backfill_plan(plan, facts)
        assert out["date_from"] == "2025-10-01"
        assert out["date_to"] == "2025-12-31"
        assert "date_from" in filled and "date_to" in filled

    def test_q4_prompt_recovers(self):
        question = "Carrier delay rate in Q4"
        facts = extract_facts(question, anchor=ANCHOR)
        assert facts.date_from == date(2025, 10, 1)
        assert facts.date_to == date(2025, 12, 31)

    def test_q1_2025_explicit_year(self):
        question = "Carrier delay rate Q1 2025"
        facts = extract_facts(question, anchor=ANCHOR)
        assert facts.date_from == date(2025, 1, 1)
        assert facts.date_to == date(2025, 3, 31)
