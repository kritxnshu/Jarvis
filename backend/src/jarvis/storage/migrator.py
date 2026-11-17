"""Numbered SQL migrations with checksums. Applied migrations are never edited."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib import resources

from jarvis.ids import utc_now_iso
from jarvis.storage.db import Database

_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_PACKAGE = "jarvis.storage.migrations"


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()


def discover(package: str = _PACKAGE) -> list[Migration]:
    found: list[Migration] = []
    for entry in resources.files(package).iterdir():
        match = _NAME.match(entry.name)
        if match:
            found.append(Migration(int(match[1]), match[2], entry.read_text(encoding="utf-8")))
    found.sort(key=lambda m: m.version)
    versions = [m.version for m in found]
    if versions != list(range(1, len(found) + 1)):
        raise MigrationError(f"migration versions must be contiguous from 1, found {versions}")
    return found


def apply_migrations(db: Database, migrations: list[Migration] | None = None) -> list[int]:
    """Apply pending migrations in order. Returns the versions applied by this call."""
    migrations = discover() if migrations is None else migrations
    db.executescript_atomic(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
        " checksum TEXT NOT NULL, applied_at TEXT NOT NULL);"
    )
    applied = {
        int(r["version"]): str(r["checksum"])
        for r in db.query("SELECT version, checksum FROM schema_migrations")
    }
    known = {m.version for m in migrations}
    unknown = sorted(set(applied) - known)
    if unknown:
        raise MigrationError(f"database has migrations this build does not know: {unknown}")
    newly: list[int] = []
    for m in migrations:
        if m.version in applied:
            if applied[m.version] != m.checksum:
                raise MigrationError(f"migration {m.version:04d}_{m.name} was modified after apply")
            continue
        # executescript takes no parameters; every value here is internal and constrained
        # (int version, [a-z0-9_] name, hex digest, generated timestamp).
        record = (
            "INSERT INTO schema_migrations (version, name, checksum, applied_at) VALUES "  # noqa: S608
            f"({m.version}, '{m.name}', '{m.checksum}', '{utc_now_iso()}');"
        )
        db.executescript_atomic(m.sql + "\n" + record)
        newly.append(m.version)
    return newly
