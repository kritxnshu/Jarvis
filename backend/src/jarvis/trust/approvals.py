"""Approvals bound to exact action digests: single-use, expiring (BRIEF §4.11, ADR-0004).

Only the executor creates requests (``request``). The API can only decide existing requests.
Highest-risk categories additionally need a native confirmation token that only the Rust shell
can compute, after the user confirms a native macOS dialog.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any

from jarvis.clock import Clock, SystemClock, from_iso, to_iso
from jarvis.ids import new_id
from jarvis.storage.db import Database
from jarvis.tools.contract import HIGHEST_RISK_CATEGORIES, ApprovalCategory, ApprovalText
from jarvis.trust.audit import AuditLog
from jarvis.trust.redaction import Redactor

NATIVE_CONFIRM_LABEL = b"jarvis-native-confirm"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    USED = "used"


class ApprovalError(Exception):
    """A refusal with a stable code. Audited after the failed transaction has rolled back."""

    def __init__(self, code: str, message: str, approval_id: str) -> None:
        super().__init__(message)
        self.code = code
        self.approval_id = approval_id


@dataclass(frozen=True)
class Approval:
    id: str
    action_id: str
    digest: str
    category: str | None
    highest_risk: bool
    request: dict[str, Any]
    status: ApprovalStatus
    created_at: str
    expires_at: str
    decided_at: str | None
    native_confirmed: bool
    used_at: str | None


def native_confirmation_token(secret: str, approval_id: str, digest: str) -> str:
    """HMAC-SHA256(secret, label || 0 || id || 0 || digest).

    Mirrored in src-tauri/src/approvals.rs; the webview never has the secret.
    """
    message = NATIVE_CONFIRM_LABEL + b"\0" + approval_id.encode() + b"\0" + digest.encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _row(r: sqlite3.Row) -> Approval:
    return Approval(
        id=r["id"],
        action_id=r["action_id"],
        digest=r["digest"],
        category=r["category"],
        highest_risk=bool(r["highest_risk"]),
        request=json.loads(r["request_json"]),
        status=ApprovalStatus(r["status"]),
        created_at=r["created_at"],
        expires_at=r["expires_at"],
        decided_at=r["decided_at"],
        native_confirmed=bool(r["native_confirmed"]),
        used_at=r["used_at"],
    )


class ApprovalService:
    def __init__(
        self,
        db: Database,
        audit: AuditLog,
        redactor: Redactor,
        native_secret: str,
        clock: Clock | None = None,
        ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        self._db = db
        self._audit = audit
        self._redactor = redactor
        self._secret = native_secret
        self._clock = clock or SystemClock()
        self._ttl = ttl

    # -- creation: executor only ------------------------------------------------------------
    def request(
        self,
        conn: sqlite3.Connection,
        *,
        action_id: str,
        task_id: str,
        digest: str,
        category: ApprovalCategory | None,
        text: ApprovalText,
        params: dict[str, Any],
    ) -> Approval:
        now = self._clock.now()
        highest = category in HIGHEST_RISK_CATEGORIES
        # Redacted before storage: approval text can quote parameters.
        request = self._redactor.redact_value({**asdict(text), "parameters": params})
        approval = Approval(
            id=new_id(),
            action_id=action_id,
            digest=digest,
            category=category.value if category else None,
            highest_risk=highest,
            request=request,
            status=ApprovalStatus.PENDING,
            created_at=to_iso(now),
            expires_at=to_iso(now + self._ttl),
            decided_at=None,
            native_confirmed=False,
            used_at=None,
        )
        conn.execute(
            "INSERT INTO approvals (id, action_id, digest, category, highest_risk, request_json,"
            " status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                approval.id,
                action_id,
                digest,
                approval.category,
                int(highest),
                json.dumps(request),
                approval.status.value,
                approval.created_at,
                approval.expires_at,
            ),
        )
        self._audit.append(
            "approval.requested",
            {
                "approval_id": approval.id,
                "action_id": action_id,
                "category": approval.category,
                "highest_risk": highest,
                "digest": digest,
                "intent": text.intent,
            },
            task_id=task_id,
            conn=conn,
        )
        return approval

    # -- reads ------------------------------------------------------------------------------
    def get(self, approval_id: str) -> Approval | None:
        rows = self._db.query("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        return _row(rows[0]) if rows else None

    def pending(self) -> list[Approval]:
        self.expire_overdue()
        rows = self._db.query(
            "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at"
        )
        return [_row(r) for r in rows]

    def expire_overdue(self) -> None:
        now = to_iso(self._clock.now())
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE approvals SET status = 'expired' WHERE status IN ('pending', 'approved')"
                " AND expires_at <= ?",
                (now,),
            )

    # -- decisions: user via the API ----------------------------------------------------------
    def decide(
        self, approval_id: str, approve: bool, native_confirmation: str | None, task_id: str | None
    ) -> Approval:
        try:
            return self._decide(approval_id, approve, native_confirmation, task_id)
        except ApprovalError as err:
            if err.code == "approval_expired":
                self.expire_overdue()
            self.audit_refusal(err, task_id, actor="user")
            raise

    def _decide(
        self, approval_id: str, approve: bool, native_confirmation: str | None, task_id: str | None
    ) -> Approval:
        with self._db.transaction() as conn:
            rows = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchall()
            if not rows:
                raise ApprovalError("approval_not_found", "no such approval", approval_id)
            approval = _row(rows[0])
            if approval.status is not ApprovalStatus.PENDING:
                raise ApprovalError(
                    "approval_not_pending", f"approval is {approval.status}", approval_id
                )
            if from_iso(approval.expires_at) <= self._clock.now():
                raise ApprovalError("approval_expired", "approval expired", approval_id)
            now = to_iso(self._clock.now())
            if not approve:
                conn.execute(
                    "UPDATE approvals SET status = 'rejected', decided_at = ? WHERE id = ?",
                    (now, approval_id),
                )
                self._audit.append(
                    "approval.rejected",
                    {"approval_id": approval_id},
                    actor="user",
                    task_id=task_id,
                    conn=conn,
                )
                return _row(
                    conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
                )
            native_ok = False
            if approval.highest_risk:
                expected = native_confirmation_token(self._secret, approval.id, approval.digest)
                native_ok = native_confirmation is not None and hmac.compare_digest(
                    native_confirmation, expected
                )
                if not native_ok:
                    raise ApprovalError(
                        "native_confirmation_required",
                        "this category needs confirmation in the native macOS dialog",
                        approval_id,
                    )
            conn.execute(
                "UPDATE approvals SET status = 'approved', decided_at = ?, native_confirmed = ?"
                " WHERE id = ?",
                (now, int(native_ok), approval_id),
            )
            self._audit.append(
                "approval.approved",
                {"approval_id": approval_id, "native_confirmed": native_ok},
                actor="user",
                task_id=task_id,
                conn=conn,
            )
            return _row(
                conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            )

    # -- consumption: executor only, inside its intent transaction ----------------------------
    def consume(self, conn: sqlite3.Connection, approval_id: str, digest: str) -> None:
        """Atomically mark an approved, unexpired approval for exactly this digest as used.

        Raises ApprovalError; the caller audits it (``audit_refusal``) after rolling back.
        """
        rows = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchall()
        if not rows:
            raise ApprovalError("approval_not_found", "no such approval", approval_id)
        approval = _row(rows[0])
        if approval.status is ApprovalStatus.USED:
            raise ApprovalError("approval_replayed", "approval already used", approval_id)
        if approval.status is not ApprovalStatus.APPROVED:
            raise ApprovalError(
                "approval_not_granted", f"approval is {approval.status}", approval_id
            )
        if from_iso(approval.expires_at) <= self._clock.now():
            raise ApprovalError("approval_expired", "approval expired", approval_id)
        if not hmac.compare_digest(approval.digest, digest):
            raise ApprovalError(
                "approval_digest_mismatch", "the action changed after it was approved", approval_id
            )
        if approval.highest_risk and not approval.native_confirmed:
            raise ApprovalError(
                "native_confirmation_required", "missing native confirmation", approval_id
            )
        cur = conn.execute(
            "UPDATE approvals SET status = 'used', used_at = ?"
            " WHERE id = ? AND status = 'approved'",
            (to_iso(self._clock.now()), approval_id),
        )
        if cur.rowcount != 1:
            raise ApprovalError("approval_replayed", "approval already used", approval_id)

    def audit_refusal(self, err: ApprovalError, task_id: str | None, actor: str = "system") -> None:
        """Record a refusal in its own transaction (the failed one has rolled back)."""
        self._audit.append(
            "approval.refused",
            {"approval_id": err.approval_id, "code": err.code},
            actor=actor,
            task_id=task_id,
        )
