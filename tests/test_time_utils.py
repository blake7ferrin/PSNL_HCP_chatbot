"""Tests for centralized time parsing and timezone conversion (src.utils.time)."""
import pytest
from datetime import datetime, timezone

from src.utils.time import (
    parse_hcp_datetime,
    to_user_tz,
    format_dt_range,
    format_single_time,
    DEFAULT_USER_TZ,
)


def test_parse_iso_with_z():
    dt = parse_hcp_datetime("2026-02-10T17:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.hour == 17
    assert dt.minute == 0


def test_parse_iso_with_offset():
    dt = parse_hcp_datetime("2026-02-10T17:00:00+00:00")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.hour == 17


def test_convert_to_america_phoenix():
    # 2026-02-10 17:00 UTC = 10:00 AM MST (America/Phoenix, no DST in Feb)
    dt = parse_hcp_datetime("2026-02-10T17:00:00Z")
    assert dt is not None
    local = to_user_tz(dt, "America/Phoenix")
    assert local.hour == 10
    assert local.minute == 0


def test_format_single_time_phoenix():
    # 17:00 UTC -> 10:00 AM MST
    s = format_single_time("2026-02-10T17:00:00Z", tz_name="America/Phoenix")
    assert "10" in s
    assert "AM" in s or "am" in s


def test_naive_assumed_utc():
    dt = parse_hcp_datetime("2026-02-10T17:00:00")
    assert dt is not None
    assert dt.tzinfo is not None


def test_format_dt_range():
    start_str, end_str, day_label = format_dt_range(
        "2026-02-10T17:00:00Z",
        "2026-02-10T22:00:00Z",
        tz_name="America/Phoenix",
    )
    assert day_label
    assert start_str
    assert end_str


def test_parse_none_empty():
    assert parse_hcp_datetime(None) is None
    assert parse_hcp_datetime("") is None
    assert parse_hcp_datetime("  ") is None


def test_parse_date_only_assumed_midnight_utc():
    dt = parse_hcp_datetime("2026-02-10")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 2 and dt.day == 10
    assert dt.hour == 0 and dt.minute == 0
    assert dt.tzinfo is not None
