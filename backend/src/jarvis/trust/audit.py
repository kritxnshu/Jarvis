"""Append-only, hash-chained audit log (BRIEF §4.12).

Each entry's hash covers its content and the previous entry's hash, so editing, deleting or
reordering any stored entry breaks verification. On a single-user machine this is tamper
*evidence*, not prevention: someone with write access can rewrite the whole chain.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from jarvis.clock import Clock, SystemClock, to_iso
from jarvis.execution.digest import canonical_json
from jarvis.storage.db import Database
from jarvis.trust.redaction import Redactor

GENESIS = "0" * 64

# Every audit event type that exists in this release. Acceptance runs assert each appears.
AUDIT_EVENT_TYPES = frozenset(
    {
        "task.created",
        "task.state_changed",
        "action.planned",
        "action.intent_recorded",
        "action.completed",
        "action.failed",
        "action.uncertain",
        "action.verified",
        "action.verification_failed",
        "action.unverifiable",
        "action.reconciled",
        "action.user_attested",
        "policy.denied",
        "approval.requested",
        "approval.approved",
        "approval.rejected",
        "approval.refused",
        "auth.rejected",
        "recovery.started",
        "permission.granted",
        "permission.revoked",
        "settings.changed",
        "provider.changed",
        "provider.credential_saved",
        "provider.credential_deleted",
        "provider.fallback",
        "chat.response",
    }
)


class UnknownAuditEventError(ValueError):
    pass


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    ts: str
    type: str
    actor: str
    task_id: str | None
    payload: dict[str, Any]
    prev_hash: str
    hash: str


@dataclass(frozen=True)
class ChainVerification:
    ok: bool
    entries: int
    first_bad_seq: int | None = None
    reason: str | None = None


def _entry_hash(
    prev_hash: str, seq: int, ts: str, type_: str, actor: str, task_id: str | None, payload: str
) -> str:
    body = canonical_json(
        {
            "seq": seq,
            "ts": ts,
            "type": type_,
            "actor": actor,
            "task_id": task_id,
            "payload": payload,
        }
    )
    return hashlib.sha256(prev_hash.encode() + body).hexdigest()


def _to_entry(r: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        seq=int(r["seq"]),
        ts=r["ts"],
        type=r["type"],
        actor=r["actor"],
        task_id=r["task_id"],
        payload=json.loads(r["payload_json"]),
        prev_hash=r["prev_hash"],
        hash=r["hash"],
    )


class AuditLog:
    def __init__(self, db: Database, redactor: Redactor, clock: Clock | None = None) -> None:
        self._db = db
        self._redactor = redactor
        self._clock = clock or SystemClock()

    def append(
        self,
        type_: str,
        payload: dict[str, Any] | None = None,
        *,
        actor: str = "system",
        task_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """Append an entry. Pass ``conn`` to join the caller's transaction."""
        if type_ not in AUDIT_EVENT_TYPES:
            raise UnknownAuditEventError(type_)
        clean = self._redactor.redact_value(payload or {})
        payload_text = canonical_json(clean).decode()
        if conn is not None:
            return self._append(conn, type_, actor, task_id, payload_text)
        with self._db.transaction() as tx:
            return self._append(tx, type_, actor, task_id, payload_text)

    def _append(
        self, conn: sqlite3.Connection, type_: str, actor: str, task_id: str | None, payload: str
    ) -> int:
        last = conn.execute("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        seq = (int(last[0]) + 1) if last else 1
        prev = str(last[1]) if last else GENESIS
        ts = to_iso(self._clock.now())
        digest = _entry_hash(prev, seq, ts, type_, actor, task_id, payload)
        conn.execute(
            "INSERT INTO audit_log (seq, ts, type, actor, task_id, payload_json, prev_hash, hash)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (seq, ts, type_, actor, task_id, payload, prev, digest),
        )
        return seq

    def verify(self) -> ChainVerification:
        prev = GENESIS
        expected_seq = 1
        rows = self._db.query(
            "SELECT seq, ts, type, actor, task_id, payload_json, prev_hash, hash"
            " FROM audit_log ORDER BY seq"
        )
        for r in rows:
            seq = int(r["seq"])
            if seq != expected_seq:
                return ChainVerification(False, len(rows), seq, "sequence gap (entry removed?)")
            if r["prev_hash"] != prev:
                return ChainVerification(False, len(rows), seq, "previous-hash mismatch")
            recomputed = _entry_hash(
                prev, seq, r["ts"], r["type"], r["actor"], r["task_id"], r["payload_json"]
            )
            if recomputed != r["hash"]:
                return ChainVerification(False, len(rows), seq, "entry content changed")
            prev = str(r["hash"])
            expected_seq += 1
        return ChainVerification(True, len(rows))

    def list(
        self,
        *,
        type_prefix: str | None = None,
        task_id: str | None = None,
        text: str | None = None,
        limit: int = 200,
        before_seq: int | None = None,
    ) -> list[AuditEntry]:
        clauses: list[str] = []
        params: list[Any] = []
        if type_prefix:
            clauses.append("type LIKE ? ESCAPE '\\'")
            params.append(type_prefix.replace("\\", "\\\\").replace("%", "\\%") + "%")
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if text:
            clauses.append("(payload_json LIKE ? ESCAPE '\\' OR type LIKE ? ESCAPE '\\')")
            needle = "%" + text.replace("\\", "\\\\").replace("%", "\\%") + "%"
            params.extend([needle, needle])
        if before_seq is not None:
            clauses.append("seq < ?")
            params.append(before_seq)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 1000)))
        rows = self._db.query(
            "SELECT seq, ts, type, actor, task_id, payload_json, prev_hash, hash FROM audit_log "  # noqa: S608
            f"{where} ORDER BY seq DESC LIMIT ?",
            params,
        )
        return [_to_entry(r) for r in rows]

    def all_entries(self) -> list[AuditEntry]:
        """Every entry, oldest first (exports are never truncated)."""
        rows = self._db.query(
            "SELECT seq, ts, type, actor, task_id, payload_json, prev_hash, hash"
            " FROM audit_log ORDER BY seq"
        )
        return [_to_entry(r) for r in rows]

    def types_present(self) -> set[str]:
        return {str(r[0]) for r in self._db.query("SELECT DISTINCT type FROM audit_log")}

    def export_json(self) -> str:
        entries = self.all_entries()
        return self._redactor.redact(json.dumps([asdict(e) for e in entries], indent=2))

    def export_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["seq", "ts", "type", "actor", "task_id", "payload", "prev_hash", "hash"])
        for e in self.all_entries():
            writer.writerow(
                [
                    e.seq,
                    e.ts,
                    e.type,
                    e.actor,
                    e.task_id or "",
                    json.dumps(e.payload),
                    e.prev_hash,
                    e.hash,
                ]
            )
        return self._redactor.redact(buf.getvalue())
