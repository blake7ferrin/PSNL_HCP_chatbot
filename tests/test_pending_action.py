"""Tests for pending action -> intent translation."""
from datetime import date

from src.intents.schema import INTENT_JOBS_LIST
from src.memory.store import PendingAction
from src.telegram.handlers import _intent_from_pending_action


def test_pending_action_builds_jobs_list_intent():
    action = PendingAction(
        intent_type="jobs.list",
        params={"start_date": "2026-02-01", "end_date": "2026-02-02", "date_label": "next week"},
        label="next week",
    )
    intent = _intent_from_pending_action(action)
    assert intent.name == INTENT_JOBS_LIST
    assert intent.filters.start_date == date(2026, 2, 1)
    assert intent.filters.end_date == date(2026, 2, 2)
    assert intent.filters.date_label == "next week"
