"""Extract literal facts (dates, regions, carriers, categories) from a
user question. Used as a belt-and-suspenders post-processor: after the LLM
returns a query plan, any field the LLM dropped is back-filled from the
user's prompt verbatim.

Why this exists:
  Even with a tightened system prompt, the LLM occasionally drops a date
  range or a filter when it rewrites a `Re: "<orig>" — use X; Y; Z.`
  follow-up. The user-visible bug: "I asked about EU in October but the
  chart was global all-time." Re-parsing the original question with the
  same regex helpers the deterministic keyword router already uses lets
  us recover the dropped facts.

Scope:
  - Re: prompt unwrapping (peels nested `Re: "<orig>" — use ...` layers
    so we extract from the user's TRUE original prompt, not the chip suffix).
  - Time-window parsing (delegates to keyword._parse_time_window) PLUS a
    month-name parser (October, Nov, etc.) anchored to the dataset's year
    range (defaults to current year when no year is mentioned).
  - region / carrier / product_category / warehouse / status detection
    (delegates to keyword helpers + a warehouse regex).

Non-goals:
  - Does NOT classify intent. The LLM still decides query vs. forecast vs.
    inspect vs. clarify. We only backfill `query_plan` fields.
  - Does NOT touch the chips themselves — those are user-selected values
    that the LLM already merged into the plan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.ai.providers.keyword import (
    CARRIERS,
    CATEGORIES,
    REGIONS,
)

# Canonical month names → 1-12.
_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Warehouses are codes like AMS-FC1, LON-FC1, ATL-DC1, …
_WAREHOUSE_RE = re.compile(r"\b[A-Z]{3}-[A-Z]{2,3}\d\b")

# Statuses we filter on.
_STATUSES = {"delivered", "delayed", "exception", "in_transit", "canceled"}


@dataclass
class ExtractedFacts:
    date_from: date | None = None
    date_to: date | None = None
    carriers: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    warehouses: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    top_n: int | None = None


# `Re: "<orig>" — use X; Y; Z.` peeling — matches the same shape the
# frontend `parseRePrompt` produces.
_RE_PROMPT_RE = re.compile(r'^Re:\s*"(.+)"\s*—\s*use\s+(.+?)\.\s*$')


def unwrap_re_prompt(question: str) -> str:
    """Peel off any number of nested Re: layers and return the inner-most
    original user question (whitespace-stripped)."""
    cur = question.strip()
    # Guard against pathological inputs (max 10 layers).
    for _ in range(10):
        m = _RE_PROMPT_RE.match(cur)
        if not m:
            break
        cur = m.group(1).strip()
    return cur


def extract_re_chips(question: str) -> list[str]:
    """Return the user-selected chip values from a Re: prompt suffix,
    in oldest-first order. Empty list if `question` is not a Re: prompt."""
    cur = question.strip()
    chips: list[str] = []
    for _ in range(10):
        m = _RE_PROMPT_RE.match(cur)
        if not m:
            break
        layer = [c.strip() for c in m.group(2).split(";") if c.strip()]
        # Outer layers were applied last; prepend so order is oldest-first.
        chips = layer + chips
        cur = m.group(1).strip()
    return chips


def _parse_month_window(q: str, default_year: int) -> tuple[date | None, date | None]:
    """Detect a month name (with optional year) and return its date range.

    Examples:
      "in October" (year=2025)            → (2025-10-01, 2025-10-31)
      "October 2024"                      → (2024-10-01, 2024-10-31)
      "back in Jan 2026"                  → (2026-01-01, 2026-01-31)
    """
    lower = q.lower()
    # Try "<month> <year>" first so we don't miss the year.
    m = re.search(
        r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|"
        r"july|jul|august|aug|september|sept|sep|october|oct|november|nov|"
        r"december|dec)\s+(\d{4})\b",
        lower,
    )
    if m:
        month = _MONTHS[m.group(1)]
        year = int(m.group(2))
    else:
        m = re.search(
            r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|"
            r"july|jul|august|aug|september|sept|sep|october|oct|november|nov|"
            r"december|dec)\b",
            lower,
        )
        if not m:
            return None, None
        month = _MONTHS[m.group(1)]
        year = default_year

    # Last day of month: jump to first of next, subtract 1 day.
    if month == 12:
        last_day = date(year, 12, 31)
    else:
        from datetime import timedelta
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    return date(year, month, 1), last_day


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _quarter_range(year: int, quarter: int) -> tuple[date, date]:
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    return date(year, start_month, 1), _last_day_of_month(year, end_month)


def _parse_relative_time(
    q: str, anchor: date
) -> tuple[date | None, date | None]:
    """Resolve relative-time phrases against `anchor` (= dataset's max date,
    NOT wall-clock today, so 'this year' on a full-2025 dataset returns
    Jan-Dec 2025 instead of Jan-May 2026).

    Handles: this/last quarter/year/month/week, Q1-Q4 [year],
    YTD/MTD/QTD/WTD, last/past N days/weeks/months/quarters/years.
    """
    lower = q.lower()

    # Q1/Q2/Q3/Q4 [year] — most specific, try first
    m = re.search(r"\bq([1-4])(?:\s+(\d{4}))?\b", lower)
    if m:
        quarter = int(m.group(1))
        year = int(m.group(2)) if m.group(2) else anchor.year
        return _quarter_range(year, quarter)

    # this/last quarter (also QTD = current quarter)
    if "this quarter" in lower or "current quarter" in lower or "qtd" in lower:
        cur_q = (anchor.month - 1) // 3 + 1
        return _quarter_range(anchor.year, cur_q)
    if "last quarter" in lower or "previous quarter" in lower:
        cur_q = (anchor.month - 1) // 3 + 1
        if cur_q == 1:
            return _quarter_range(anchor.year - 1, 4)
        return _quarter_range(anchor.year, cur_q - 1)

    # this/last year (YTD = current year)
    if "this year" in lower or "ytd" in lower or "year to date" in lower:
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    if "last year" in lower or "previous year" in lower:
        return date(anchor.year - 1, 1, 1), date(anchor.year - 1, 12, 31)

    # this/last month (MTD = current month)
    if "this month" in lower or "mtd" in lower or "month to date" in lower:
        return (
            date(anchor.year, anchor.month, 1),
            _last_day_of_month(anchor.year, anchor.month),
        )
    if "last month" in lower or "previous month" in lower:
        if anchor.month == 1:
            return date(anchor.year - 1, 12, 1), date(anchor.year - 1, 12, 31)
        return (
            date(anchor.year, anchor.month - 1, 1),
            _last_day_of_month(anchor.year, anchor.month - 1),
        )

    # this/last week (WTD = current week, ISO Mon-Sun)
    if "this week" in lower or "wtd" in lower or "week to date" in lower:
        monday = anchor - timedelta(days=anchor.weekday())
        return monday, anchor
    if "last week" in lower or "previous week" in lower:
        cur_monday = anchor - timedelta(days=anchor.weekday())
        last_monday = cur_monday - timedelta(days=7)
        return last_monday, last_monday + timedelta(days=6)

    # last/past N days/weeks/months/quarters/years
    m = re.search(
        r"\b(?:last|past)\s+(\d+)\s+(day|week|month|quarter|year)s?\b", lower
    )
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit == "day":
            return anchor - timedelta(days=n), anchor
        if unit == "week":
            return anchor - timedelta(days=n * 7), anchor
        if unit == "month":
            # Interpretation C: "last N months" = current month + previous
            # (N-1) complete months. For N=3, anchor=Dec 30 → Oct 1 → Dec 30.
            # Matches Salesforce/HubSpot "Last N Months" filter convention.
            month_idx = anchor.month - n + 1
            year = anchor.year
            while month_idx <= 0:
                month_idx += 12
                year -= 1
            return date(year, month_idx, 1), anchor
        if unit == "quarter":
            cur_q = (anchor.month - 1) // 3 + 1
            target_q = cur_q - n
            year = anchor.year
            while target_q <= 0:
                target_q += 4
                year -= 1
            start, _ = _quarter_range(year, target_q)
            return start, anchor
        if unit == "year":
            try:
                return date(anchor.year - n, anchor.month, anchor.day), anchor
            except ValueError:
                # Feb 29 leap-year edge
                return date(anchor.year - n, anchor.month, 28), anchor

    # "today" / "yesterday"
    if re.search(r"\btoday\b", lower):
        return anchor, anchor
    if re.search(r"\byesterday\b", lower):
        y = anchor - timedelta(days=1)
        return y, y

    return None, None


def _parse_top_n(q: str) -> int | None:
    """Detect explicit Top-N requests: 'top 10', 'top-10', 'top10',
    '10 worst', '5 highest', etc. Clamped to [1, 50] (matches QueryPlan
    + safety allow-list). Returns None when no explicit number is given."""
    lower = q.lower()
    m = re.search(r"\btop[\s\-]?(\d{1,2})\b", lower)
    if m:
        return max(1, min(50, int(m.group(1))))
    m = re.search(
        r"\b(\d{1,2})\s+(worst|best|highest|lowest|most|biggest|smallest|fastest|slowest)\b",
        lower,
    )
    if m:
        return max(1, min(50, int(m.group(1))))
    return None


def extract_facts(
    question: str,
    default_year: int | None = None,
    anchor: date | None = None,
) -> ExtractedFacts:
    """Parse literal facts out of `question`.

    Always unwraps Re: layers first, so we extract from the user's true
    original prompt, not the chip-merge suffix.

    `anchor` defaults to Dec 31 of `default_year` when not given (so the
    dataset's max date is the relative-time anchor — important for full-2025
    demo data being queried from May 2026).
    """
    orig = unwrap_re_prompt(question)

    # Resolve anchor: prefer explicit, else derive from default_year, else today.
    if anchor is None:
        if default_year is not None:
            anchor = date(default_year, 12, 31)
        else:
            anchor = date.today()

    # Time window resolution priority:
    #   1. relative time (this/last quarter/year/month/week, last N units, Q1-Q4)
    #   2. month name (October, Oct 2025)
    # Whichever fires first wins; the LLM's date (if it set one) is preserved
    # by backfill_plan because backfill is non-destructive.
    df, dt = _parse_relative_time(orig, anchor)
    if df is None and dt is None:
        year = default_year if default_year is not None else anchor.year
        df, dt = _parse_month_window(orig, default_year=year)

    facts = ExtractedFacts(date_from=df, date_to=dt)
    facts.top_n = _parse_top_n(orig)

    lower = orig.lower()
    facts.carriers = [c for c in CARRIERS if c.lower() in lower]
    facts.regions = [r for r in REGIONS if r.lower() in lower]
    facts.categories = [c for c in CATEGORIES if c.lower() in lower]
    facts.warehouses = _WAREHOUSE_RE.findall(orig)
    facts.statuses = [s for s in _STATUSES if s in lower]

    # Also classify chip values from the `Re: ... — use X; Y; Z.` suffix:
    # these are the user's clarification answers and must be treated as
    # filter values, not as dimension keywords (which are handled by the LLM).
    for chip in extract_re_chips(question):
        chip_lower = chip.lower()
        # Try carrier first (most specific).
        for c in CARRIERS:
            if c.lower() == chip_lower and c not in facts.carriers:
                facts.carriers.append(c)
                break
        for r in REGIONS:
            if r.lower() == chip_lower and r not in facts.regions:
                facts.regions.append(r)
                break
        for c in CATEGORIES:
            if c.lower() == chip_lower and c not in facts.categories:
                facts.categories.append(c)
                break
        if _WAREHOUSE_RE.fullmatch(chip) and chip not in facts.warehouses:
            facts.warehouses.append(chip)
        if chip_lower in _STATUSES and chip_lower not in facts.statuses:
            facts.statuses.append(chip_lower)
    return facts


def backfill_plan(
    plan_dict: dict,
    facts: ExtractedFacts,
    dataset_range: tuple | None = None,
) -> tuple[dict, list[str]]:
    """Backfill empty plan fields from extracted facts.

    Returns (new_plan_dict, list_of_fields_filled).

    For non-date scalar fields (carrier, region, ...): conservative —
    only fills when the LLM left the slot empty.

    For dates: AGGRESSIVE override. When the prompt contains a parseable
    relative-time phrase ("last 3 months", "this quarter", "yesterday"),
    the deterministic anchor-based resolution wins over whatever the LLM
    picked. This guarantees v1 and v2 produce IDENTICAL date windows for
    the same prompt — eliminating the LLM's freedom to pick "rolling 90
    days" vs "calendar months back" vs "current + previous N-1 months".
    Free-form ranges like "between Mar 5 and Apr 12" still pass through
    because ``_parse_relative_time`` returns (None, None) for them.

    The ``dataset_range`` argument is currently unused (the canonical
    override fires regardless of dataset overlap) but kept in the
    signature for backwards compatibility and future safety nets.
    """
    filled: list[str] = []
    out = dict(plan_dict)

    if facts.date_from is not None and facts.date_to is not None:
        new_from = facts.date_from.isoformat()
        new_to = facts.date_to.isoformat()
        if out.get("date_from") != new_from:
            out["date_from"] = new_from
            filled.append("date_from")
        if out.get("date_to") != new_to:
            out["date_to"] = new_to
            if "date_to" not in filled:
                filled.append("date_to")

    if out.get("date_from") is None and facts.date_from is not None:
        out["date_from"] = facts.date_from.isoformat()
        filled.append("date_from")
    if out.get("date_to") is None and facts.date_to is not None:
        out["date_to"] = facts.date_to.isoformat()
        filled.append("date_to")

    for plan_key, fact_attr in (
        ("carrier", "carriers"),
        ("region", "regions"),
        ("category", "categories"),
        ("warehouse", "warehouses"),
        ("status", "statuses"),
    ):
        existing = out.get(plan_key) or []
        extracted = getattr(facts, fact_attr)
        if not existing and extracted:
            out[plan_key] = list(extracted)
            filled.append(plan_key)

    # top_n: special-case. The user explicitly mentioned a number in the
    # prompt; if the LLM either left it None OR returned a different value,
    # honour the user's explicit number. (Conservative for None; assertive
    # for explicit-but-different because that's almost always an LLM drop.)
    if facts.top_n is not None:
        existing_top_n = out.get("top_n")
        if existing_top_n is None or existing_top_n != facts.top_n:
            out["top_n"] = facts.top_n
            filled.append("top_n")
    return out, filled
