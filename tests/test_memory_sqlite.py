"""SQLite-backed memory store round-trip tests."""
from datetime import date

from src.memory.sqlite_store import SQLiteMemoryStore
from src.memory.store import AnchorDateRange, PendingAction


def test_sqlite_store_round_trip(tmp_path):
    db_path = tmp_path / "bot.db"
    store = SQLiteMemoryStore(db_path=str(db_path))
    state = store.get("chat-1")
    state.set_anchor(
        "job",
        ids=["job_123"],
        date_range=AnchorDateRange(date(2026, 2, 9), date(2026, 2, 9)),
        label="today",
    )
    state.set_pending_action(
        PendingAction(
            intent_type="jobs.list",
            params={"start_date": "2026-02-09", "end_date": "2026-02-09", "date_label": "today"},
            label="today",
        )
    )
    store.save(state)

    store2 = SQLiteMemoryStore(db_path=str(db_path))
    loaded = store2.get("chat-1")
    assert loaded.last_anchor is not None
    assert loaded.last_anchor.type == "job"
    assert loaded.last_anchor.ids == ["job_123"]
    assert loaded.last_anchor.date_range is not None
    assert loaded.last_anchor.date_range.start == date(2026, 2, 9)
    assert loaded.pending_action is not None
    assert loaded.pending_action.intent_type == "jobs.list"
    assert loaded.pending_action.params["date_label"] == "today"
