"""Persistence for user settings. Values are stored as JSON text."""

from __future__ import annotations

import json
from typing import Any

from jarvis.ids import utc_now_iso
from jarvis.storage.db import Database


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def all(self) -> dict[str, Any]:
        rows = self._db.query("SELECT key, value_json FROM settings")
        return {str(r["key"]): json.loads(r["value_json"]) for r in rows}

    def put(self, key: str, value: Any) -> str:
        updated_at = utc_now_iso()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=excluded.updated_at",
                (key, json.dumps(value), updated_at),
            )
        return updated_at
