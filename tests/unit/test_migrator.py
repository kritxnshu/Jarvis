from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.storage.db import Database
from jarvis.storage.migrator import Migration, MigrationError, apply_migrations, discover


def test_discovered_migrations_are_contiguous() -> None:
    migrations = discover()
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))


def test_apply_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.sqlite3")
    first = apply_migrations(db)
    assert first == [m.version for m in discover()]
    assert apply_migrations(db) == []
    assert db.query("PRAGMA journal_mode")[0][0] == "wal"
    db.close()


def test_modified_migration_is_refused(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.sqlite3")
    apply_migrations(db, [Migration(1, "a", "CREATE TABLE a (x);")])
    with pytest.raises(MigrationError, match="modified"):
        apply_migrations(db, [Migration(1, "a", "CREATE TABLE a (x, y);")])
    db.close()


def test_unknown_applied_migration_is_refused(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.sqlite3")
    apply_migrations(db, [Migration(1, "a", "CREATE TABLE a (x);"), Migration(2, "b", "SELECT 1;")])
    with pytest.raises(MigrationError, match="does not know"):
        apply_migrations(db, [Migration(1, "a", "CREATE TABLE a (x);")])
    db.close()


def test_failed_migration_is_rolled_back(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.sqlite3")
    bad = Migration(1, "bad", "CREATE TABLE ok (x); THIS IS NOT SQL;")
    with pytest.raises(Exception, match="syntax"):
        apply_migrations(db, [bad])
    tables = {r[0] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ok" not in tables
    assert db.query("SELECT COUNT(*) FROM schema_migrations")[0][0] == 0
    db.close()


def test_database_file_is_private(tmp_path: Path) -> None:
    db = Database(tmp_path / "t.sqlite3")
    assert (tmp_path / "t.sqlite3").stat().st_mode & 0o777 == 0o600
    db.close()
