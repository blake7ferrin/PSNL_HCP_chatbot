"""Tests for per-chat memory (src.memory)."""
from datetime import date

from src.memory import AnchorDateRange, InMemoryStore, get_chat_memory, set_memory_store


def _reset_store():
    set_memory_store(InMemoryStore())


def test_update_after_job_get_sets_entity():
    _reset_store()
    mem = get_chat_memory("test-chat-job-get")
    mem.update_after_intent("job.get", entity_type="job", entity_id="job_456")
    ctx = mem.to_context()
    assert ctx["last_entity_type"] == "job"
    assert ctx["last_entity_id"] == "job_456"
    assert ctx["last_intent"] == "job.get"


def test_set_anchor_and_get_anchor():
    _reset_store()
    mem = get_chat_memory("test-chat-anchor")
    assert mem.last_anchor is None
    mem.set_anchor(
        "job",
        ids=["job_1", "job_2"],
        date_range=AnchorDateRange(date(2026, 2, 9), date(2026, 2, 15)),
        label="next week",
    )
    anchor = mem.last_anchor
    assert anchor is not None
    assert anchor.type == "job"
    assert anchor.ids == ["job_1", "job_2"]
    assert anchor.date_range is not None
    assert anchor.date_range.start == date(2026, 2, 9)
    assert anchor.date_range.end == date(2026, 2, 15)
    assert anchor.label == "next week"
    assert mem.last_entity_ids == ["job_1", "job_2"]
    assert mem.last_entity_id == "job_1"


def test_clear_anchor():
    _reset_store()
    mem = get_chat_memory("test-chat-clear-anchor")
    mem.set_anchor("job", ids=["job_123"])
    assert mem.last_anchor is not None
    mem.clear_anchor()
    assert mem.last_anchor is None


def test_to_context_includes_last_anchor():
    _reset_store()
    mem = get_chat_memory("test-chat-to-context-anchor")
    mem.set_anchor("job", ids=["job_1"], label="today")
    ctx = mem.to_context()
    assert "last_anchor" in ctx
    assert ctx["last_anchor"]["type"] == "job"
    assert ctx["last_anchor"]["ids"] == ["job_1"]
    assert ctx["last_anchor"]["label"] == "today"


def test_anchor_filters_wrong_prefix():
    _reset_store()
    mem = get_chat_memory("test-chat-anchor-filter")
    mem.set_anchor("job", ids=["cus_123", "job_456"])
    assert mem.last_anchor is not None
    assert mem.last_anchor.ids == ["job_456"]
