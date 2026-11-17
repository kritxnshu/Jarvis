"""In-process trust kernel for unit/acceptance tests (no subprocess, manual clock)."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from jarvis.clock import ManualClock
from jarvis.services import Services, build_services
from jarvis.storage.db import Database
from jarvis.storage.migrator import apply_migrations
from jarvis.trust.approvals import native_confirmation_token
from jarvis.trust.redaction import Redactor
from tests.fixtures.tools import build_fixture_registry

SECRET = "ab" * 32


@contextmanager
def kernel(tmp_path: Path) -> Generator[tuple[Services, ManualClock]]:
    db = Database(tmp_path / "k.sqlite3")
    apply_migrations(db)
    redactor = Redactor()
    redactor.register(SECRET)
    clock = ManualClock()
    try:
        yield build_services(db, redactor, SECRET, build_fixture_registry(), clock), clock
    finally:
        db.close()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def native_token(approval_id: str, digest: str) -> str:
    """What the Rust shell sends after the user confirms the native dialog."""
    return native_confirmation_token(SECRET, approval_id, digest)
