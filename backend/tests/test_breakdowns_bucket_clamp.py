"""Session 36.2 — bucket label clamping.

The weekly bucketer rounds order_date down to its ISO Monday. When the user
filters `date_from=Wed Oct 1`, an order on Oct 1 used to get the bucket label
"2025-09-29" (Monday of that week) — visually misleading because the user
never asked for September. Same risk for month granularity if date_from falls
mid-month. _bucket_key now clamps the label to date_from.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.analytics.breakdowns import _bucket_key, orders_over_time
from app.repositories.base import Filters


# ---------- pure _bucket_key unit tests ----------

class TestBucketKeyWeek:
    def test_week_no_clamp_when_min_date_none(self):
        # Wed Oct 1, 2025 → Mon Sep 29, 2025
        assert _bucket_key(date(2025, 10, 1), "week") == "2025-09-29"

    def test_week_clamps_when_iso_monday_before_min_date(self):
        # Filter starts Oct 1 (Wed). Monday of that week = Sep 29 → must clamp.
        assert (
            _bucket_key(date(2025, 10, 1), "week", min_date=date(2025, 10, 1))
            == "2025-10-01"
        )

    def test_week_no_clamp_when_iso_monday_on_or_after_min_date(self):
        # Mon Oct 6 is its own ISO Monday and >= min_date → unchanged.
        assert (
            _bucket_key(date(2025, 10, 8), "week", min_date=date(2025, 10, 1))
            == "2025-10-06"
        )

    def test_week_clamp_only_affects_first_partial_bucket(self):
        # Oct 5 (Sun) belongs to week of Sep 29 → clamped to Oct 1.
        # Oct 6 (Mon) starts a new week → label = Oct 6 (no clamp).
        assert _bucket_key(date(2025, 10, 5), "week", min_date=date(2025, 10, 1)) == "2025-10-01"
        assert _bucket_key(date(2025, 10, 6), "week", min_date=date(2025, 10, 1)) == "2025-10-06"


class TestBucketKeyMonth:
    def test_month_no_clamp_when_min_date_none(self):
        assert _bucket_key(date(2025, 10, 15), "month") == "2025-10"

    def test_month_clamps_when_first_of_month_before_min_date(self):
        # Filter starts Oct 15. Order on Oct 20 → first-of-month = Oct 1 < Oct 15
        # → label clamps to "2025-10" (the min_date's month).
        assert (
            _bucket_key(date(2025, 10, 20), "month", min_date=date(2025, 10, 15))
            == "2025-10"
        )

    def test_month_no_clamp_when_first_of_month_on_or_after_min_date(self):
        # min_date = Oct 1 exactly → first_of_month is NOT < min_date → no clamp.
        assert (
            _bucket_key(date(2025, 11, 5), "month", min_date=date(2025, 10, 1))
            == "2025-11"
        )


class TestBucketKeyDay:
    def test_day_ignores_min_date(self):
        # Day granularity isn't a "rounding" bucket — labels match the date.
        assert _bucket_key(date(2025, 10, 1), "day") == "2025-10-01"
        assert (
            _bucket_key(date(2025, 10, 1), "day", min_date=date(2025, 11, 1))
            == "2025-10-01"
        )


# ---------- orders_over_time integration with a fake repo ----------


class _FakeRepo:
    def __init__(self, orders: list[dict[str, Any]]):
        self._orders = orders

    def fetch_orders(self, filters: Filters) -> list[dict[str, Any]]:
        # Tests pass already-filtered data; bucketing is what's under test.
        return list(self._orders)


def _ord(d: date, status: str = "delivered") -> dict[str, Any]:
    return {"order_date": d, "status": status}


class TestOrdersOverTimeWeeklyClamp:
    def test_first_bucket_label_is_clamped_to_date_from(self):
        # Orders on Wed Oct 1 + Sun Oct 5 are in the same ISO week (Mon Sep 29).
        # With date_from=Oct 1 they must aggregate under "2025-10-01", not "2025-09-29".
        repo = _FakeRepo([_ord(date(2025, 10, 1)), _ord(date(2025, 10, 5))])
        rows = orders_over_time(
            repo, Filters(date_from=date(2025, 10, 1), date_to=date(2025, 12, 30)), "week"
        )
        assert rows[0]["period"] == "2025-10-01"
        assert rows[0]["total"] == 2
        # No bucket should ever be earlier than date_from.
        assert all(r["period"] >= "2025-10-01" for r in rows)

    def test_subsequent_weeks_are_not_clamped(self):
        repo = _FakeRepo([
            _ord(date(2025, 10, 1)),   # → bucket 2025-10-01 (clamped)
            _ord(date(2025, 10, 6)),   # → bucket 2025-10-06 (Mon, unchanged)
            _ord(date(2025, 10, 27)),  # → bucket 2025-10-27 (Mon, unchanged)
        ])
        rows = orders_over_time(
            repo, Filters(date_from=date(2025, 10, 1), date_to=date(2025, 12, 30)), "week"
        )
        periods = [r["period"] for r in rows]
        assert periods == ["2025-10-01", "2025-10-06", "2025-10-27"]

    def test_no_filter_means_no_clamp(self):
        # When no date_from is set, original ISO-Monday labelling is preserved
        # (back-compat — doesn't break callers that don't pass a window).
        repo = _FakeRepo([_ord(date(2025, 10, 1))])
        rows = orders_over_time(repo, Filters(), "week")
        assert rows[0]["period"] == "2025-09-29"
