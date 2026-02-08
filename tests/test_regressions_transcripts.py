"""Regression tests for transcript failures: anchors, confirm, and follow-ups."""
import asyncio
from datetime import date

from src.compose.formatter import extract_job_ids_from_list
from src.hcp import jobs as hcp_jobs
from src.intents.router import route
from src.intents.schema import (
    Intent,
    IntentFilters,
    INTENT_CONFIRM,
    INTENT_JOBS_LIST,
    INTENT_UNKNOWN,
)
from src.memory.store import ChatMemory
from src.telegram.handlers import _dispatch


def _filters_for_day(day: date, label: str) -> IntentFilters:
    f = IntentFilters()
    f.start_date = day
    f.end_date = day
    f.date_label = label
    return f


def test_extract_job_ids_skips_customer_prefixed_ids():
    """jobs.list should never anchor cus_* ids as job ids."""
    data = {"jobs": [{"id": "cus_123"}, {"id": "job_456"}]}
    assert extract_job_ids_from_list(data) == ["job_456"]


def test_extract_job_ids_prefers_job_id_over_customer_id():
    """If job_id exists, use it even when id looks like a customer."""
    data = {"jobs": [{"id": "cus_999", "job_id": "job_abc"}]}
    assert extract_job_ids_from_list(data) == ["job_abc"]


def test_the_one_with_multiple_jobs_requires_clarification():
    """'the one' should not auto-pick first job when multiple exist."""
    ctx = {"resolved_entity": {"type": "job", "ids": ["j1", "j2"], "date_range": None}}
    r = route("the one", context=ctx)
    assert r.name == INTENT_UNKNOWN
    assert (r.raw_slots or {}).get("clarification") == "multiple_jobs"


def test_confirm_dispatch_uses_pending_action_from_memory(monkeypatch):
    """'yes please' should execute pending_action stored in memory and clear it."""
    async def fake_list_jobs(*args, **kwargs):
        return {"jobs": []}

    monkeypatch.setattr(hcp_jobs, "list_jobs", fake_list_jobs)
    monkeypatch.setenv("COMPOSE_TONE", "neutral_professional")

    f = _filters_for_day(date(2026, 2, 1), "Feb 1")
    mem = ChatMemory(chat_id="test-confirm-memory")
    mem.set_pending_action({"intent": INTENT_JOBS_LIST, "filters": f})

    reply, use_md, ids = asyncio.run(
        _dispatch(Intent(INTENT_CONFIRM), "yes please", memory=mem, tz_name="America/Phoenix")
    )

    assert mem.pending_action is None
    assert "No jobs" in reply
    assert use_md is True
    assert ids == []


def test_confirm_dispatch_uses_pending_action_from_intent_slots(monkeypatch):
    """Confirm should execute pending_action from intent slots even without memory."""
    async def fake_list_jobs(*args, **kwargs):
        return {"jobs": []}

    monkeypatch.setattr(hcp_jobs, "list_jobs", fake_list_jobs)
    monkeypatch.setenv("COMPOSE_TONE", "neutral_professional")

    f = _filters_for_day(date(2026, 2, 2), "Feb 2")
    intent = Intent(
        INTENT_CONFIRM,
        raw_slots={"pending_action": {"intent": INTENT_JOBS_LIST, "filters": f}},
    )

    reply, use_md, ids = asyncio.run(
        _dispatch(intent, "yes", memory=ChatMemory(chat_id="test-confirm-slots"), tz_name="America/Phoenix")
    )

    assert "No jobs" in reply
    assert use_md is True
    assert ids == []
