"""Unit tests for human date parsing (intents.dateparse)."""
import pytest
from datetime import date

from src.intents.dateparse import parse_human_date, DateRange, DEFAULT_TZ


def test_today():
    r = parse_human_date("today", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start == r.end
    assert r.start == date.today()


def test_tomorrow():
    from datetime import timedelta
    r = parse_human_date("tomorrow", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start == r.end
    assert r.start == date.today() + timedelta(days=1)


def test_yesterday():
    from datetime import timedelta
    r = parse_human_date("yesterday", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start == date.today() - timedelta(days=1)


def test_next_week_range():
    r = parse_human_date("next week", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start < r.end
    # Next week = next Monday through Sunday
    assert r.start.weekday() == 0
    assert r.end.weekday() == 6
    assert (r.end - r.start).days == 6


def test_this_week():
    r = parse_human_date("this week", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start.weekday() == 0
    assert r.end.weekday() == 6


def test_last_week():
    r = parse_human_date("last week", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.label == "last week"
    assert r.start.weekday() == 0
    assert r.end.weekday() == 6
    assert (r.end - r.start).days == 6
    # Last week should be before this week
    from datetime import timedelta
    this_week_monday = date.today() - timedelta(days=date.today().weekday())
    assert r.end < this_week_monday


def test_next_7_days():
    r = parse_human_date("next 7 days", tz_name=DEFAULT_TZ)
    assert r is not None
    from datetime import timedelta
    assert r.start == date.today()
    assert r.end == date.today() + timedelta(days=6)


def test_iso_date():
    r = parse_human_date("2026-02-07", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start == date(2026, 2, 7)
    assert r.end == date(2026, 2, 7)


def test_month_name_date():
    r = parse_human_date("Jan 30", tz_name=DEFAULT_TZ)
    assert r is not None
    y = date.today().year
    assert r.start == date(y, 1, 30)


def test_month_name_with_year():
    r = parse_human_date("January 30 2025", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start == date(2025, 1, 30)


def test_bare_weekday():
    r = parse_human_date("Tuesday", tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start.weekday() == 1  # Tuesday


def test_follow_up_tuesday_in_range():
    # "Tuesday" when context is next week -> Tuesday of that week
    start = date(2026, 2, 9)   # Monday
    end = date(2026, 2, 15)   # Sunday
    r = parse_human_date("Tuesday", context_start=start, context_end=end, tz_name=DEFAULT_TZ)
    assert r is not None
    assert r.start == date(2026, 2, 10)  # Tuesday that week


def test_empty_returns_none():
    assert parse_human_date("") is None
    assert parse_human_date("   ") is None


def test_gibberish_returns_none_or_weekday():
    r = parse_human_date("xyzabc")
    assert r is None
    r2 = parse_human_date("next Monday")
    assert r2 is not None
    assert r2.start.weekday() == 0
