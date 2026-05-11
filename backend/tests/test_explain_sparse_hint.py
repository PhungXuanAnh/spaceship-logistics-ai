"""Tests for the sparse-result hint in explain()."""
from app.ai.explain import explain


def _plan(top_n=5, **extra):
    base = {
        "metric": "delivered_count",
        "dimension": "carrier",
        "region": ["EU"],
        "status": ["delivered"],
        "date_from": "2025-10-01",
        "date_to": "2025-10-31",
        "top_n": top_n,
    }
    base.update(extra)
    return base


def test_hint_appears_when_rows_less_than_top_n():
    text = explain(_plan(top_n=5), tool="query", row_count=1, provider="claude")
    assert "only 1 of the requested top 5" in text
    assert "broadening the date range" in text


def test_no_hint_when_rows_equal_top_n():
    text = explain(_plan(top_n=5), tool="query", row_count=5, provider="claude")
    assert "only" not in text.lower() or "only 5 of the requested" not in text


def test_no_hint_when_rows_exceed_top_n():
    text = explain(_plan(top_n=5), tool="query", row_count=9, provider="claude")
    assert "of the requested top" not in text


def test_no_hint_when_top_n_is_one():
    # "highest carrier" naturally returns 1 — don't nag.
    text = explain(_plan(top_n=1), tool="query", row_count=1, provider="claude")
    assert "of the requested top" not in text


def test_no_hint_when_zero_rows():
    # Zero is a different problem (empty result); the row-count line already says "0".
    text = explain(_plan(top_n=5), tool="query", row_count=0, provider="claude")
    assert "of the requested top" not in text


def test_no_hint_when_top_n_missing():
    plan = _plan(top_n=5)
    plan.pop("top_n")
    text = explain(plan, tool="query", row_count=1, provider="claude")
    assert "of the requested top" not in text


def test_hint_includes_filter_advice():
    text = explain(_plan(top_n=10), tool="query", row_count=2, provider="gemini-native")
    assert "only 2 of the requested top 10" in text
    assert "Try broadening" in text
