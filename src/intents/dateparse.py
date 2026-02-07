"""Normalize human date phrases to (start_dt, end_dt) in user timezone.

Supports: today, tomorrow, yesterday, last week, next week, this week, next 7 days,
this weekend, explicit dates (Jan 30), and follow-up day references (e.g. "Tuesday"
meaning next Tuesday or Tuesday within last referenced range).
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/Phoenix"

# Weekday names (Python: Monday=0, Sunday=6)
_WEEKDAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


@dataclass
class DateRange:
    """Start and end date (inclusive) plus human-readable label."""
    start: date
    end: date
    label: str


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _today_in_tz(tz_name: str) -> date:
    tz = ZoneInfo(tz_name)
    return datetime.now(tz=tz).date()


def parse_human_date(
    text: str,
    *,
    context_start: Optional[date] = None,
    context_end: Optional[date] = None,
    tz_name: str = DEFAULT_TZ,
) -> Optional[DateRange]:
    """
    Parse a human date phrase into a date range in the user's timezone.

    - context_start/context_end: when user said "next week" then "Tuesday",
      pass the last range so "Tuesday" is resolved to Tuesday within that range.
    - Returns DateRange(start, end, label) or None if unparseable.
    """
    if not text or not text.strip():
        return None
    normalized = _normalize(text)
    today = _today_in_tz(tz_name)

    # ---- Single day: today / tomorrow / yesterday (exact or as word in sentence) ----
    if normalized in ("today", "todays") or re.search(r"\btoday\b", normalized):
        return DateRange(today, today, "today")
    if normalized in ("tomorrow", "tomorrows") or re.search(r"\btomorrow\b", normalized):
        d = today + timedelta(days=1)
        return DateRange(d, d, "tomorrow")
    if normalized in ("yesterday", "yesterdays") or re.search(r"\byesterday\b", normalized):
        d = today - timedelta(days=1)
        return DateRange(d, d, "yesterday")

    # ---- ISO date ----
    if re.match(r"^\d{4}-\d{2}-\d{2}$", normalized):
        try:
            d = date.fromisoformat(normalized)
            return DateRange(d, d, d.strftime("%a %b %d"))
        except ValueError:
            pass

    # ---- Numeric: MM/DD or MM/DD/YYYY ----
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$", normalized)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            d = date(year, month, day)
            return DateRange(d, d, d.strftime("%a %b %d"))
        except ValueError:
            pass

    # ---- Month name + day: Jan 30, January 30th, Jan. 30 2026 ----
    month_match = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s*\.?\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
        normalized,
        re.I,
    )
    if month_match:
        month_str, day_str, year_str = month_match.group(1).lower(), month_match.group(2), month_match.group(3)
        month = _MONTH_NAMES.get(month_str)
        if month is not None:
            day = int(day_str)
            year = int(year_str) if year_str else today.year
            try:
                d = date(year, month, day)
                return DateRange(d, d, d.strftime("%a %b %d"))
            except ValueError:
                pass

    # ---- "Last week" = previous Monday through Sunday ----
    if re.search(r"\blast\s+week\b", normalized) or re.search(r"\bprevious\s+week\b", normalized) or re.search(r"\bpast\s+week\b", normalized):
        # This week's Monday minus 7 days = last Monday
        this_week_monday = today - timedelta(days=today.weekday())
        last_monday = this_week_monday - timedelta(days=7)
        last_sunday = last_monday + timedelta(days=6)
        return DateRange(last_monday, last_sunday, "last week")

    # ---- "Next week" = next Monday 00:00 through next Sunday 23:59 ----
    if re.search(r"\bnext\s+week\b", normalized):
        days_until_next_monday = (7 - today.weekday()) % 7
        if days_until_next_monday == 0:
            days_until_next_monday = 7
        next_monday = today + timedelta(days=days_until_next_monday)
        next_sunday = next_monday + timedelta(days=6)
        return DateRange(next_monday, next_sunday, "next week")

    # ---- "This week" = Monday through Sunday of current week ----
    if re.search(r"\bthis\s+week\b", normalized):
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return DateRange(week_start, week_end, "this week")

    # ---- "Next 7 days" (including today) ----
    if re.search(r"\bnext\s*7\s*days?\b", normalized) or re.search(r"\b7\s*days?\s*(?:ahead|from now|out)\b", normalized):
        end = today + timedelta(days=6)
        return DateRange(today, end, "next 7 days")

    # ---- "This weekend" = this coming Saturday and Sunday ----
    if re.search(r"\bthis\s+weekend\b", normalized):
        days_until_sat = (5 - today.weekday() + 7) % 7
        if days_until_sat == 0 and today.weekday() != 5:
            days_until_sat = 7
        sat = today + timedelta(days=days_until_sat)
        sun = sat + timedelta(days=1)
        return DateRange(sat, sun, "this weekend")

    # ---- "Next Monday" / "next Tuesday" etc. (single day) ----
    weekday_match = re.search(
        r"\bnext\s+(monday|tue(?:sday)?|tues|wed(?:nesday)?|thu(?:rsday)?|thur(?:sday)?|thurs|"
        r"fri(?:day)?|sat(?:urday)?|sun(?:day)?|mon)\b",
        normalized,
    )
    if weekday_match:
        name = weekday_match.group(1).lower()
        wd = _WEEKDAY_NAMES.get(name)
        if wd is not None:
            delta = (wd - today.weekday() + 7) % 7
            if delta == 0:
                delta = 7
            d = today + timedelta(days=delta)
            return DateRange(d, d, d.strftime("%A %b %d"))

    # ---- Follow-up: "Tuesday" / "any day next week" style ----
    # If we have a context range, resolve bare weekday to that day within range
    if context_start is not None and context_end is not None:
        bare_weekday = re.search(
            r"\b(monday|tue(?:sday)?|tues|wed(?:nesday)?|thu(?:rsday)?|thur(?:sday)?|thurs|"
            r"fri(?:day)?|sat(?:urday)?|sun(?:day)?|mon)\b",
            normalized,
        )
        if bare_weekday:
            name = bare_weekday.group(1).lower()
            wd = _WEEKDAY_NAMES.get(name)
            if wd is not None:
                d = context_start
                while d <= context_end:
                    if d.weekday() == wd:
                        return DateRange(d, d, d.strftime("%A %b %d"))
                    d += timedelta(days=1)
                # No such weekday in range: use next occurrence after context
                d = context_end + timedelta(days=1)
                while d.weekday() != wd:
                    d += timedelta(days=1)
                return DateRange(d, d, d.strftime("%A %b %d"))

    # ---- Bare weekday without context: next upcoming occurrence ----
    bare = re.search(
        r"\b(monday|tue(?:sday)?|tues|wed(?:nesday)?|thu(?:rsday)?|thur(?:sday)?|thurs|"
        r"fri(?:day)?|sat(?:urday)?|sun(?:day)?|mon)\b",
        normalized,
    )
    if bare:
        name = bare.group(1).lower()
        wd = _WEEKDAY_NAMES.get(name)
        if wd is not None:
            delta = (wd - today.weekday() + 7) % 7
            if delta == 0:
                delta = 7
            d = today + timedelta(days=delta)
            return DateRange(d, d, d.strftime("%A %b %d"))

    return None
