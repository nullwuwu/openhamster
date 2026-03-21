from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import get_settings


def _runtime_state_path() -> Path:
    settings = get_settings()
    return Path(settings.storage.runtime_state_db_path)


def _connect() -> sqlite3.Connection:
    path = _runtime_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_kv (
            key TEXT PRIMARY KEY NOT NULL,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def init_runtime_state_store() -> None:
    conn = _connect()
    conn.close()


def get_runtime_state_json(key: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT value_json FROM runtime_kv WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row["value_json"]))
        return dict(value) if isinstance(value, dict) else None
    finally:
        conn.close()


def set_runtime_state_json(
    key: str,
    value_json: dict[str, Any],
    *,
    updated_at: datetime,
    retries: int = 5,
    retry_sleep_seconds: float = 0.1,
) -> None:
    payload = json.dumps(value_json, ensure_ascii=False, sort_keys=True)
    updated_at_value = updated_at.isoformat()
    for attempt in range(retries):
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO runtime_kv (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, payload, updated_at_value),
            )
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if "database is locked" not in str(exc).lower() or attempt >= retries - 1:
                raise
            time.sleep(retry_sleep_seconds * (attempt + 1))
        finally:
            conn.close()


def delete_runtime_state_keys(keys: list[str]) -> None:
    if not keys:
        return
    conn = _connect()
    try:
        conn.executemany("DELETE FROM runtime_kv WHERE key = ?", [(key,) for key in keys])
        conn.commit()
    finally:
        conn.close()
