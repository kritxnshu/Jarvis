"""SQLite connection with the pragmas JARVIS relies on (WAL, foreign keys, durable commits)."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

Params = Sequence[Any] | dict[str, Any]


class Database:
    """A single shared connection guarded by a lock; callers use short transactions."""

    def __init__(self, path: Path, busy_timeout_ms: int = 5000) -> None:
        self.path = path
        is_new = not path.exists()
        self._conn = sqlite3.connect(
            path, check_same_thread=False, isolation_level=None, timeout=busy_timeout_ms / 1000
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        if is_new:
            path.chmod(0o600)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def query(self, sql: str, params: Params = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def executescript_atomic(self, script: str) -> None:
        """Run a multi-statement script inside one transaction (all or nothing)."""
        with self._lock:
            try:
                self._conn.executescript(f"BEGIN IMMEDIATE;\n{script}\nCOMMIT;")
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()
