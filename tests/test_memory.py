"""Tests for per-chat memory (src.memory.store)."""
import pytest
from datetime import date

from src.memory.store import ChatMemory, get_chat_memory


def test_update_after_job_get_sets_entity():
    mem = get_chat_memory("test-chat-job-get")
    mem.update_after_intent("job.get", entity_type="job", entity_id="job-456")
    ctx = mem.to_context()
    assert ctx["last_entity_type"] == "job"
    assert ctx["last_entity_id"] == "job-456"
    assert ctx["last_intent"] == "job.get"


def test_set_anchor_and_get_anchor():
    mem = get_chat_memory("test-chat-anchor")
    assert mem.get_anchor() is None
    mem.set_anchor("job", ids=["job-1", "job-2"], date_range=(date(2026, 2, 9), date(2026, 2, 15)), label="next week")
    anchor = mem.get_anchor()
    assert anchor is not None
    assert anchor["type"] == "job"
    assert anchor["ids"] == ["job-1", "job-2"]
    assert anchor["date_range"] == (date(2026, 2, 9), date(2026, 2, 15))
    assert anchor["label"] == "next week"
    assert mem.last_entity_ids == ["job-1", "job-2"]
    assert mem.last_entity_id == "job-1"


def test_clear_anchor():
    mem = get_chat_memory("test-chat-clear-anchor")
    mem.set_anchor("job", ids=["job-x"])
    assert mem.get_anchor() is not None
    mem.clear_anchor()
    assert mem.get_anchor() is None


def test_to_context_includes_last_anchor():
    mem = get_chat_memory("test-chat-to-context-anchor")
    mem.set_anchor("job", ids=["j1"], label="today")
    ctx = mem.to_context()
    assert "last_anchor" in ctx
    assert ctx["last_anchor"]["type"] == "job"
    assert ctx["last_anchor"]["ids"] == ["j1"]
    assert ctx["last_anchor"]["label"] == "today"
