"""Daily metrics (counts only) stored in SQLite."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _db_path() -> str:
    return os.getenv("BOT_DB_PATH", "").strip() or "./data/bot.db"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _record_metric(metric_name: str, value: int, *, day: Optional[str] = None) -> None:
    if value is None:
        return
    day_key = day or date.today().isoformat()
    try:
        conn = _connect()
        with conn:
            conn.execute(
                """
                INSERT INTO metrics_daily (day, metric_name, value_int, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(day, metric_name) DO UPDATE SET
                    value_int = value_int + excluded.value_int,
                    updated_at = excluded.updated_at;
                """,
                (day_key, metric_name, int(value), _utc_now_iso()),
            )
        conn.close()
    except Exception as e:
        logger.debug("metrics record failed: %s", e)


def record_jobs_list(count: int, *, day: Optional[str] = None) -> None:
    _record_metric("jobs_listed", count, day=day)


def record_estimates_list(count: int, *, day: Optional[str] = None) -> None:
    _record_metric("estimates_listed", count, day=day)
