"""Centralized datetime parsing and timezone conversion. All HCP timestamps treated as UTC."""
import logging
from datetime import date, datetime, time, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

DEFAULT_USER_TZ = "America/Phoenix"


def parse_hcp_datetime(ts: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO8601 timestamp from HCP. Always return timezone-aware datetime in UTC.
    Accepts: "2026-02-10T17:00:00Z", "2026-02-10T17:00:00+00:00", "2026-02-10T17:00:00".
    Date-only "2026-02-10" treated as midnight UTC (log warning).
    If ts has no tzinfo, assume UTC (log warning).
    Returns None if ts is None/empty or unparseable.
    """
    if ts is None or (isinstance(ts, str) and not ts.strip()):
        return None
    s = str(ts).strip()
    if "T" not in s:
        try:
            d = date.fromisoformat(s[:10])
            dt = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
            logger.warning("time: date-only timestamp %s assumed midnight UTC", ts)
            return dt
        except ValueError:
            return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            logger.warning("time: naive timestamp %s assumed UTC", ts)
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception as e:
        logger.debug("time: parse_hcp_datetime failed for %s: %s", ts, e)
        return None


def to_user_tz(dt: datetime, tz_name: str = DEFAULT_USER_TZ) -> datetime:
    """Convert timezone-aware datetime to user timezone. Uses zoneinfo (py3.9+)."""
    if dt.tzinfo is None:
        logger.warning("time: to_user_tz received naive datetime, assuming UTC")
        dt = dt.replace(tzinfo=timezone.utc)
    if ZoneInfo is None:
        return dt
    return dt.astimezone(ZoneInfo(tz_name))


def format_dt_range(
    start_ts: Optional[str],
    end_ts: Optional[str],
    tz_name: str = DEFAULT_USER_TZ,
) -> Tuple[str, str, str]:
    """
    Parse start/end HCP timestamps, convert to user TZ, format for display.
    Returns (start_str, end_str, day_label).
    start_str/end_str are like "10:00 AM", "4:00 PM"; day_label is "Mon Feb 10".
    """
    start_dt = parse_hcp_datetime(start_ts)
    end_dt = parse_hcp_datetime(end_ts)
    if start_dt is None:
        return ("", "", "")
    start_local = to_user_tz(start_dt, tz_name)
    end_local = to_user_tz(end_dt, tz_name) if end_dt else start_local
    # Format time (e.g. 10:00 AM)
    start_str = start_local.strftime("%I:%M %p").lstrip("0")
    end_str = end_local.strftime("%I:%M %p").lstrip("0") if end_dt else ""
    day_label = start_local.strftime("%a %b %d")
    return (start_str, end_str, day_label)


def format_single_time(ts: Optional[str], tz_name: str = DEFAULT_USER_TZ) -> str:
    """Parse one HCP timestamp and return local time string (e.g. '10:00 AM')."""
    dt = parse_hcp_datetime(ts)
    if dt is None:
        return ""
    local = to_user_tz(dt, tz_name)
    return local.strftime("%I:%M %p").lstrip("0")


def format_schedule_line(
    start_ts: Optional[str],
    end_ts: Optional[str],
    tz_name: str = DEFAULT_USER_TZ,
    *,
    arrival_window_hours: Optional[float] = None,
) -> str:
    """
    One-line schedule for a job: "Scheduled Tue Feb 10, 10:00 AM–4:00 PM (America/Phoenix). Arrival window: 2h (if available)."
    """
    start_str, end_str, day_label = format_dt_range(start_ts, end_ts, tz_name=tz_name)
    if not day_label and not start_str:
        return "No schedule time available."
    time_part = f"{start_str}–{end_str}" if end_str else start_str
    line = f"Scheduled {day_label}, {time_part} ({tz_name})."
    if arrival_window_hours is not None and arrival_window_hours > 0:
        h = int(arrival_window_hours) if arrival_window_hours == int(arrival_window_hours) else arrival_window_hours
        line += f" Arrival window: {h}h."
    return line
