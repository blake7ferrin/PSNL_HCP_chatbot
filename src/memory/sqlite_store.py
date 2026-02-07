"""SQLite-backed conversation memory store (WAL enabled)."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .store import (
    ChatState,
    ConversationAnchor,
    PendingAction,
    DEFAULT_TZ,
)

DB_SCHEMA_VERSION = 1

_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS chat_state (
            chat_id TEXT PRIMARY KEY,
            timezone TEXT,
            last_intent TEXT,
            last_start_date TEXT,
            last_end_date TEXT,
            last_date_label TEXT,
            last_entity_ids_json TEXT,
            last_entity_type TEXT,
            last_entity_id TEXT,
            last_anchor_json TEXT,
            pending_action_json TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS metrics_daily (
            day TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value_int INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (day, metric_name)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            timestamp TEXT NOT NULL,
            chat_id TEXT,
            user_id TEXT,
            intent_type TEXT,
            ok INTEGER,
            error_code TEXT
        );
        """,
    ),
]


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _serialize_anchor(anchor: Optional[ConversationAnchor]) -> Optional[str]:
    if not anchor:
        return None
    return json.dumps(anchor.to_dict(), separators=(",", ":"))


def _deserialize_anchor(raw: Optional[str]) -> Optional[ConversationAnchor]:
    if not raw:
        return None
    try:
        return ConversationAnchor.from_dict(json.loads(raw))
    except Exception:
        return None


def _serialize_pending(action: Optional[PendingAction]) -> Optional[str]:
    if not action:
        return None
    return json.dumps(action.to_dict(), separators=(",", ":"))


def _deserialize_pending(raw: Optional[str]) -> Optional[PendingAction]:
    if not raw:
        return None
    try:
        return PendingAction.from_dict(json.loads(raw))
    except Exception:
        return None


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except Exception:
        return None


class SQLiteMemoryStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        path = db_path or os.getenv("BOT_DB_PATH", "").strip() or "./data/bot.db"
        self.db_path = str(path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._apply_pragmas()
        self._apply_migrations()

    def _apply_pragmas(self) -> None:
        cur = self._conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        self._conn.commit()

    def _apply_migrations(self) -> None:
        cur = self._conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);")
        row = cur.execute("SELECT MAX(version) AS version FROM schema_version;").fetchone()
        current = int(row["version"]) if row and row["version"] is not None else 0
        if current == 0:
            cur.execute("DELETE FROM schema_version;")
            cur.execute("INSERT INTO schema_version (version) VALUES (0);")
        for version, sql in _MIGRATIONS:
            if version > current:
                cur.executescript(sql)
                cur.execute("UPDATE schema_version SET version = ?;", (version,))
                current = version
        self._conn.commit()

    def get(self, chat_id: str) -> ChatState:
        key = str(chat_id)
        cur = self._conn.cursor()
        row = cur.execute("SELECT * FROM chat_state WHERE chat_id = ?;", (key,)).fetchone()
        if not row:
            return ChatState(chat_id=key)
        state = ChatState(
            chat_id=key,
            timezone=row["timezone"] or DEFAULT_TZ,
            last_intent=row["last_intent"] or None,
            last_start_date=_parse_date(row["last_start_date"]),
            last_end_date=_parse_date(row["last_end_date"]),
            last_date_label=row["last_date_label"] or None,
            last_entity_ids=json.loads(row["last_entity_ids_json"]) if row["last_entity_ids_json"] else [],
            last_entity_type=row["last_entity_type"] or None,
            last_entity_id=row["last_entity_id"] or None,
            last_anchor=_deserialize_anchor(row["last_anchor_json"]),
            pending_action=_deserialize_pending(row["pending_action_json"]),
        )
        return state

    def save(self, state: ChatState) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO chat_state (
                chat_id, timezone, last_intent, last_start_date, last_end_date,
                last_date_label, last_entity_ids_json, last_entity_type, last_entity_id,
                last_anchor_json, pending_action_json, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(chat_id) DO UPDATE SET
                timezone=excluded.timezone,
                last_intent=excluded.last_intent,
                last_start_date=excluded.last_start_date,
                last_end_date=excluded.last_end_date,
                last_date_label=excluded.last_date_label,
                last_entity_ids_json=excluded.last_entity_ids_json,
                last_entity_type=excluded.last_entity_type,
                last_entity_id=excluded.last_entity_id,
                last_anchor_json=excluded.last_anchor_json,
                pending_action_json=excluded.pending_action_json,
                updated_at=excluded.updated_at;
            """,
            (
                str(state.chat_id),
                state.timezone,
                state.last_intent,
                state.last_start_date.isoformat() if state.last_start_date else None,
                state.last_end_date.isoformat() if state.last_end_date else None,
                state.last_date_label,
                json.dumps(state.last_entity_ids, separators=(",", ":")),
                state.last_entity_type,
                state.last_entity_id,
                _serialize_anchor(state.last_anchor),
                _serialize_pending(state.pending_action),
                _utc_now_iso(),
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def get_db_status(db_path: Optional[str] = None) -> dict[str, str | int | bool]:
    path = db_path or os.getenv("BOT_DB_PATH", "").strip() or "./data/bot.db"
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT MAX(version) AS version FROM schema_version;").fetchone()
        version = int(row["version"]) if row and row["version"] is not None else 0
        conn.close()
        return {"ok": True, "schema_version": version, "path": path}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": path}
