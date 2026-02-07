"""Deterministic Ops Coach: suggest next queries from returned data. Read-only suggestions only."""
from typing import Any


def money_no_total_suggestions() -> list[str]:
    """Suggestions when a job has no total (e.g. not yet invoiced). One primary + one alternative."""
    return [
        "Want me to check if there's an estimate for this job?",
        "Want to see completed jobs with invoices?",
    ]


def money_aggregation_suggestions(date_label: str) -> list[str]:
    """Single follow-up suggestion when user asked for total collected / revenue (we can't compute)."""
    return [f"Want me to list jobs from {date_label} instead?"]


def money_dead_end_suggestions() -> list[str]:
    """Suggestions for money-related dead ends (no total, unsupported aggregation, etc.)."""
    return [
        "List jobs with invoices",
        "List paid invoices",
        "Show estimates awaiting approval",
        "Show completed jobs without invoices",
    ]

# Thresholds (tunable)
LOW_JOBS_THRESHOLD = 3
MANY_JOBS_PER_DAY_THRESHOLD = 5


def _list_from_response(data: Any) -> list:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "estimates", "customers", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def _job_date_str(obj: dict) -> str | None:
    start = (
        obj.get("scheduled_start_date")
        or obj.get("scheduled_start")
        or obj.get("start_date")
    )
    if start is None and isinstance(obj.get("schedule"), dict):
        start = obj["schedule"].get("scheduled_start") or obj["schedule"].get("scheduled_start_date")
    if start is None:
        return None
    if isinstance(start, str):
        return start.split("T")[0][:10]
    return None


def _job_assigned_tech(obj: dict) -> bool:
    pro = obj.get("pro") or obj.get("technician") or obj.get("assigned_to")
    if isinstance(pro, dict):
        return bool(pro.get("id") or pro.get("name"))
    return bool(pro)


def ops_coach_suggestions(
    jobs_data: Any,
    *,
    date_label: str = "",
    max_suggestions: int = 3,
) -> list[str]:
    """
    Return 2–3 short suggested next actions based on job list data.
    Deterministic heuristics only; no LLM.
    """
    jobs = _list_from_response(jobs_data)
    suggestions: list[str] = []

    if not jobs:
        suggestions.append("Show unscheduled estimates")
        suggestions.append("Show open estimates")
        suggestions.append("Show tomorrow" if date_label != "tomorrow" else "Show next 7 days")
        return suggestions[:max_suggestions]

    total = len(jobs)
    by_day: dict[str, list] = {}
    unassigned = 0
    for j in jobs:
        obj = j if isinstance(j, dict) else {}
        d = _job_date_str(obj)
        if d:
            by_day.setdefault(d, []).append(obj)
        if not _job_assigned_tech(obj):
            unassigned += 1

    if total < LOW_JOBS_THRESHOLD:
        suggestions.append("List unscheduled estimates to fill the calendar")
    if unassigned > 0:
        suggestions.append("List unassigned jobs")
    max_per_day = max(len(v) for v in by_day.values()) if by_day else 0
    if max_per_day >= MANY_JOBS_PER_DAY_THRESHOLD:
        suggestions.append("View load by tech for that period")
    if not suggestions:
        suggestions.append("Show next 7 days")
        suggestions.append("Show open estimates")
    return suggestions[:max_suggestions]
