from __future__ import annotations

import itertools
import json
import sqlite3
from pathlib import Path

import pytest

from jarvis.trust.audit import GENESIS, UnknownAuditEventError
from tests.conftest import CANARY
from tests.support.kernel import kernel


def test_chain_verifies_and_links(tmp_path: Path) -> None:
    with kernel(tmp_path) as (s, _):
        for i in range(5):
            s.audit.append("settings.changed", {"i": i})
        result = s.audit.verify()
        assert result.ok
        assert result.entries == 5
        entries = sorted(s.audit.list(), key=lambda e: e.seq)
        assert entries[0].prev_hash == GENESIS
        for prev, cur in itertools.pairwise(entries):
            assert cur.prev_hash == prev.hash


def test_triggers_block_update_and_delete(tmp_path: Path) -> None:
    with kernel(tmp_path) as (s, _):
        s.audit.append("settings.changed", {"x": 1})
        for sql in ("UPDATE audit_log SET actor = 'evil'", "DELETE FROM audit_log"):
            with (
                pytest.raises(sqlite3.IntegrityError, match="append-only"),
                s.db.transaction() as c,
            ):
                c.execute(sql)


@pytest.mark.parametrize(
    "tamper",
    [
        "UPDATE audit_log SET payload_json = '{\"x\":999}' WHERE seq = 2",
        "UPDATE audit_log SET type = 'auth.rejected' WHERE seq = 2",
        "UPDATE audit_log SET ts = '2000-01-01T00:00:00.000Z' WHERE seq = 2",
        "DELETE FROM audit_log WHERE seq = 2",
    ],
    ids=["payload", "type", "timestamp", "delete"],
)
def test_modifying_a_stored_entry_breaks_verification(tmp_path: Path, tamper: str) -> None:
    with kernel(tmp_path) as (s, _):
        for i in range(4):
            s.audit.append("settings.changed", {"x": i})
        # Bypass the guard triggers the way an attacker with file access could.
        with s.db.transaction() as c:
            c.execute("DROP TRIGGER audit_log_no_update")
            c.execute("DROP TRIGGER audit_log_no_delete")
            c.execute(tamper)
        result = s.audit.verify()
        assert not result.ok
        assert result.first_bad_seq in (2, 3)


def test_secrets_are_redacted_before_writing_and_in_exports(tmp_path: Path) -> None:
    with kernel(tmp_path) as (s, _):
        s.audit.append("settings.changed", {"note": f"key={CANARY}", CANARY: [CANARY]})
        assert CANARY not in json.dumps([e.payload for e in s.audit.list()])
        assert CANARY not in s.audit.export_json()
        assert CANARY not in s.audit.export_csv()
        s.db.close()
        for f in tmp_path.iterdir():
            assert CANARY.encode() not in f.read_bytes(), f


def test_unknown_event_types_are_refused(tmp_path: Path) -> None:
    with kernel(tmp_path) as (s, _), pytest.raises(UnknownAuditEventError):
        s.audit.append("made.up", {})


def test_search_and_exports(tmp_path: Path) -> None:
    with kernel(tmp_path) as (s, _):
        s.audit.append("settings.changed", {"key": "alpha"})
        s.audit.append("auth.rejected", {"reason": "missing"})
        assert [e.type for e in s.audit.list(type_prefix="auth.")] == ["auth.rejected"]
        assert [e.payload["key"] for e in s.audit.list(text="alpha")] == ["alpha"]
        assert len(json.loads(s.audit.export_json())) == 2
        assert s.audit.export_csv().splitlines()[0].startswith("seq,ts,type")
