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


def test_estimates_list():
    assert route("list estimates").name == INTENT_ESTIMATES_LIST
    assert route("estimates").name == INTENT_ESTIMATES_LIST


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
