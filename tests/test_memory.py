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
