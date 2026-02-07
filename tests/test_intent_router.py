"""Unit tests for intent routing (intents.router)."""
import pytest
from datetime import date

from src.intents.router import route
from src.intents.schema import (
    INTENT_JOBS_LIST,
    INTENT_JOB_GET,
    INTENT_JOB_TIME,
    INTENT_ESTIMATES_LIST,
    INTENT_ESTIMATE_GET,
    INTENT_CUSTOMERS_SEARCH,
    INTENT_CUSTOMER_GET,
    INTENT_PRICEBOOK_SEARCH,
    INTENT_COMPANY_INFO,
    INTENT_STATS,
    INTENT_HELP,
    INTENT_AGGREGATION_UNSUPPORTED,
    INTENT_UNKNOWN,
)


def test_help_intent():
    assert route("help").name == INTENT_HELP
    assert route("what can you do").name == INTENT_HELP
    assert route("Hi").name == INTENT_HELP


def test_job_get_by_id():
    r = route("job 12345")
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "12345"
    r2 = route("get job 999")
    assert r2.name == INTENT_JOB_GET
    assert r2.entity_id == "999"


def test_estimate_get():
    r = route("estimate 678")
    assert r.name == INTENT_ESTIMATE_GET
    assert r.entity_id == "678"


def test_customer_get():
    r = route("customer 789")
    assert r.name == INTENT_CUSTOMER_GET
    assert r.entity_id == "789"


def test_jobs_list_today():
    r = route("jobs today")
    assert r.name == INTENT_JOBS_LIST
    assert r.filters.start_date == date.today()
    assert r.filters.end_date == date.today()


def test_jobs_next_week():
    r = route("jobs next week")
    assert r.name == INTENT_JOBS_LIST
    assert r.filters.start_date is not None
    assert r.filters.end_date is not None
    assert r.filters.start_date < r.filters.end_date
    assert r.filters.start_date.weekday() == 0
    assert r.filters.end_date.weekday() == 6


def test_any_day_next_week():
    r = route("any day next week")
    assert r.name == INTENT_JOBS_LIST
    assert r.filters.date_label is not None


def test_jobs_last_week():
    r = route("What jobs did we have last week?")
    assert r.name == INTENT_JOBS_LIST
    assert r.filters.date_label == "last week"
    assert r.filters.start_date is not None
    assert r.filters.end_date is not None
    assert r.filters.start_date < r.filters.end_date


def test_aggregation_total_collected_last_week():
    """Aggregation questions route to INTENT_AGGREGATION_UNSUPPORTED, not jobs.list."""
    r = route("What was our total collected amount last week?")
    assert r.name == INTENT_AGGREGATION_UNSUPPORTED
    assert r.name != INTENT_JOBS_LIST
    assert r.filters.date_label == "last week"
    assert r.filters.start_date is not None
    assert r.filters.end_date is not None


def test_aggregation_revenue_this_week():
    r = route("revenue this week")
    assert r.name == INTENT_AGGREGATION_UNSUPPORTED
    assert r.name != INTENT_JOBS_LIST


def test_aggregation_how_much_did_we_make():
    r = route("how much did we make last week?")
    assert r.name == INTENT_AGGREGATION_UNSUPPORTED


def test_estimates_list():
    assert route("list estimates").name == INTENT_ESTIMATES_LIST
    assert route("estimates").name == INTENT_ESTIMATES_LIST


def test_estimates_list_unscheduled_open():
    r = route("Show unscheduled estimates")
    assert r.name == INTENT_ESTIMATES_LIST
    assert r.filters.status == "unscheduled"
    r = route("Show open estimates")
    assert r.name == INTENT_ESTIMATES_LIST
    assert r.filters.status == "open"


def test_customers_list():
    assert route("list customers").name == INTENT_CUSTOMERS_SEARCH
    assert route("customers").name == INTENT_CUSTOMERS_SEARCH


def test_company_info():
    assert route("company info").name == INTENT_COMPANY_INFO
    assert route("company setup").name == INTENT_COMPANY_INFO


def test_pricebook():
    assert route("pricebook").name == INTENT_PRICEBOOK_SEARCH
    assert route("services").name == INTENT_PRICEBOOK_SEARCH


def test_stats():
    assert route("stats").name == INTENT_STATS
    assert route("summary").name == INTENT_STATS
    assert route("how's it looking").name == INTENT_STATS


def test_unknown():
    r = route("xyz random gibberish")
    assert r.name == INTENT_UNKNOWN
    assert route("").name == INTENT_UNKNOWN


def test_follow_up_tuesday_with_context():
    ctx = {
        "last_intent": INTENT_JOBS_LIST,
        "last_start_date": "2026-02-09",
        "last_end_date": "2026-02-15",
        "last_date_label": "next week",
    }
    r = route("what about Tuesday?", context=ctx)
    assert r.name == INTENT_JOBS_LIST
    assert r.filters.start_date == date(2026, 2, 10)
    assert r.filters.end_date == date(2026, 2, 10)


def test_the_second_one_with_context():
    ctx = {
        "last_intent": INTENT_JOBS_LIST,
        "last_entity_ids": ["job-a", "job-b", "job-c"],
    }
    r = route("show me the second one", context=ctx)
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "job-b"


def test_list_index_without_context_unknown():
    r = route("the third one", context={})
    assert r.name == INTENT_UNKNOWN


def test_what_time_with_job_context():
    ctx = {"last_entity_type": "job", "last_entity_id": "job-123"}
    r = route("what time is it at?", context=ctx)
    assert r.name == INTENT_JOB_TIME
    assert r.entity_id == "job-123"


def test_what_time_without_context_unknown():
    r = route("what time is it at?", context={})
    assert r.name == INTENT_UNKNOWN
    assert r.raw_slots.get("hint", "").startswith("Which job?")


def test_total_on_that_one_with_job_list_context():
    ctx = {"last_intent": INTENT_JOBS_LIST, "last_entity_id": "job-abc", "last_entity_ids": ["job-abc"]}
    r = route("what's the total on that one?", context=ctx)
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "job-abc"


def test_details_next_weeks_job_with_context():
    ctx = {"last_intent": INTENT_JOBS_LIST, "last_entity_ids": ["job-xyz"]}
    r = route("details on next weeks job?", context=ctx)
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "job-xyz"


# ---- Conversation anchor: resolved_entity (injected by handler when anchor + reference phrase) ----

def test_resolved_entity_total_on_that_one():
    """jobs.list → 'what's the total on that one?' → job.get with correct ID."""
    ctx = {"resolved_entity": {"type": "job", "ids": ["job-abc"], "date_range": None}}
    r = route("what's the total on that one?", context=ctx)
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "job-abc"


def test_resolved_entity_details_next_weeks_job():
    """jobs.list(next week, 1 job) → 'details on next weeks job' → job.get."""
    ctx = {"resolved_entity": {"type": "job", "ids": ["job-xyz"], "date_range": None}}
    r = route("details on next weeks job", context=ctx)
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "job-xyz"


def test_resolved_entity_multiple_jobs_that_one_clarification():
    """jobs.list(2 jobs) → 'that one' (no ordinal) → clarification question."""
    ctx = {"resolved_entity": {"type": "job", "ids": ["j1", "j2"], "date_range": None}}
    r = route("that one", context=ctx)
    assert r.name == INTENT_UNKNOWN
    assert (r.raw_slots or {}).get("clarification") == "multiple_jobs"


def test_resolved_entity_multiple_jobs_second_one_resolved():
    """jobs.list(2 jobs) → 'the second one' → job.get with second ID."""
    ctx = {"resolved_entity": {"type": "job", "ids": ["j1", "j2"], "date_range": None}}
    r = route("the second one", context=ctx)
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "j2"


def test_no_anchor_that_one_polite_clarification():
    """No anchor → 'that one' → polite clarification (no_job)."""
    ctx = {"reference_phrase_used": True}
    r = route("that one", context=ctx)
    assert r.name == INTENT_UNKNOWN
    assert (r.raw_slots or {}).get("clarification") == "no_job"


def test_resolved_entity_total_gets_focus_money():
    """'what's the total?' with single job in anchor → job.get with focus=money."""
    ctx = {"resolved_entity": {"type": "job", "ids": ["job-123"], "date_range": None}}
    r = route("what's the total on that one?", context=ctx)
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "job-123"
    assert getattr(r, "focus", None) == "money"


def test_resolved_entity_total_amount_without_that_one():
    """'what's the total?' (no 'that one') with single job in anchor → job.get with focus=money."""
    ctx = {"resolved_entity": {"type": "job", "ids": ["job-456"], "date_range": None}}
    r = route("what's the total?", context=ctx)
    assert r.name == INTENT_JOB_GET
    assert r.entity_id == "job-456"
    assert getattr(r, "focus", None) == "money"


def test_resolved_entity_zero_ids_no_job_clarification():
    """Anchor with 0 jobs → 'that one' → no_job clarification."""
    ctx = {"resolved_entity": {"type": "job", "ids": [], "date_range": None}}
    r = route("that one", context=ctx)
    assert r.name == INTENT_UNKNOWN
    assert (r.raw_slots or {}).get("clarification") == "no_job"
