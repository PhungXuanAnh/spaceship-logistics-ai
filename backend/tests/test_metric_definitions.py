"""Pinned-number tests for the delay_rate / on_time_rate metric definitions.

These tests are deliberately tight — they assert the *exact* numbers that come
out of the demo CSV (`data/mock_logistics_data.csv`) so any drift in the metric
formula (numerator, denominator, status-set membership, rounding) is caught
immediately. Cross-checked against a hand computation done directly on the CSV.

Status counts in the demo dataset:
    delivered=304, delayed=55, exception=11, in_transit=27, canceled=3, total=400

So the canonical numbers are:
    completed             = 304 + 55 + 11 = 370
    delayed_orders        = 55 + 11      = 66    (delayed includes exception)
    on_time_delivery_rate = 304 / 370    = 0.8216
    delay_rate (overall)  =  66 / 370    = 0.1784

Per-carrier ground truth (sorted by delay_rate desc):
    GLS       9 ord (5d / 3D / 1in / 0can) → completed=8,  delay_rate=0.375
    USPS     49 ord (35d /12D / 2in / 0can) → completed=47, delay_rate=0.2553
    UPS      88 ord (59d /19D / 8in / 2can) → completed=78, delay_rate=0.2436
    Royal …  26 ord (19d / 6D / 1in / 0can) → completed=25, delay_rate=0.24
    OnTrac   29 ord (21d / 6D / 2in / 0can) → completed=27, delay_rate=0.2222
    FedEx    89 ord (73d /12D / 4in / 0can) → completed=85, delay_rate=0.1412
    DPD      20 ord (16d / 2D / 2in / 0can) → completed=18, delay_rate=0.1111
    LaserShp 27 ord (22d / 2D / 2in / 1can) → completed=24, delay_rate=0.0833
    DHL      63 ord (54d / 4D / 5in / 0can) → completed=58, delay_rate=0.069

(d = delivered, D = delayed+exception, in = in_transit, can = canceled)
"""
from __future__ import annotations

from app.analytics import breakdowns, kpis
from app.repositories.base import Filters
from app.repositories.sqlalchemy_orders import SqlAlchemyOrderRepository


def test_compute_kpis_pinned_numbers(db_session):
    """Top-level KPIs must match the hand-computed ground truth exactly."""
    repo = SqlAlchemyOrderRepository(db_session)
    k = kpis.compute_kpis(repo, Filters())
    assert k["total_orders"] == 400
    assert k["delivered_orders"] == 304
    # delayed_orders counts BOTH 'delayed' (55) AND 'exception' (11) statuses
    assert k["delayed_orders"] == 66, (
        "delayed_orders must include both 'delayed' and 'exception' rows; "
        "if this fails, DELAYED_STATUSES probably dropped 'exception'"
    )
    # on_time_rate = delivered / (delivered + delayed + exception) = 304/370
    assert k["on_time_delivery_rate"] == round(304 / 370, 4) == 0.8216


def test_breakdown_by_carrier_exposes_completed_denominator(db_session):
    """Every breakdown row must surface the denominator used for delay_rate.

    Without `completed`, a reader/interview question of "what's the denominator
    of this rate?" can only be answered by re-deriving it from the row schema,
    which is exactly the kind of footgun this field eliminates.
    """
    repo = SqlAlchemyOrderRepository(db_session)
    rows = breakdowns.breakdown_by(repo, Filters(), "carrier")
    assert all("completed" in r for r in rows), (
        "Every breakdown row must include 'completed' (= delivered + delayed + exception)"
    )
    # `completed` must equal `delivered + delayed` per row (since `delayed`
    # already counts both 'delayed' and 'exception' statuses)
    for r in rows:
        assert r["completed"] == r["delivered"] + r["delayed"]


def test_breakdown_by_carrier_pinned_numbers_for_extremes(db_session):
    """Pin the worst (GLS) and best (DHL) carriers exactly."""
    repo = SqlAlchemyOrderRepository(db_session)
    rows = breakdowns.breakdown_by(repo, Filters(), "carrier")
    by_carrier = {r["carrier"]: r for r in rows}

    gls = by_carrier["GLS"]
    assert gls["total"] == 9
    assert gls["delivered"] == 5
    assert gls["delayed"] == 3  # 2 delayed + 1 exception
    assert gls["completed"] == 8
    assert gls["delay_rate"] == 0.375  # 3/8

    dhl = by_carrier["DHL"]
    assert dhl["total"] == 63
    assert dhl["delivered"] == 54
    assert dhl["delayed"] == 4  # 3 delayed + 1 exception
    assert dhl["completed"] == 58
    assert dhl["delay_rate"] == round(4 / 58, 4) == 0.069


def test_top_n_worst_carriers_by_delay_rate(db_session):
    """The 'top 3 worst carriers by delay rate' UX prompt — pin the answer.

    With the existing min_completed >= 5 guard, GLS (8 completed) qualifies.
    Order must be GLS > USPS > UPS based on the hand-computed delay rates.
    """
    repo = SqlAlchemyOrderRepository(db_session)
    rows = breakdowns.top_n_by(repo, Filters(), "carrier", "delay_rate", n=3)
    assert [r["carrier"] for r in rows] == ["GLS", "USPS", "UPS"]
    assert [r["delay_rate"] for r in rows] == [0.375, 0.2553, 0.2436]
    # And the denominator field must be present so the UI/LLM can show it
    assert all("completed" in r for r in rows)
    assert [r["completed"] for r in rows] == [8, 47, 78]


def test_in_transit_and_canceled_excluded_from_rate_denominator(db_session):
    """Regression guard: if someone changes the formula to use `total` as the
    denominator (which would include in_transit + canceled), GLS would drop
    from 0.375 to 0.333 (3/9) — catch that immediately."""
    repo = SqlAlchemyOrderRepository(db_session)
    rows = breakdowns.breakdown_by(repo, Filters(), "carrier")
    gls = next(r for r in rows if r["carrier"] == "GLS")
    # If the denominator were wrong (= total instead of completed), this would
    # be 3/9 = 0.3333. The defensible value is 3/8 = 0.375.
    assert gls["delay_rate"] != round(3 / 9, 4)
    assert gls["delay_rate"] == 0.375
