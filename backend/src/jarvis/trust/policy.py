"""Deterministic policy engine. Model output never reaches this code as an argument."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from jarvis.clock import Clock, SystemClock, from_iso, to_iso
from jarvis.ids import new_id
from jarvis.storage.db import Database
from jarvis.tools.contract import PermissionNeed, Risk


class Verdict(StrEnum):
    ALLOW = "allow"
    NEEDS_APPROVAL = "needs_approval"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyDecision:
    verdict: Verdict
    reason: str


@dataclass(frozen=True)
class Grant:
    id: str
    scope_type: str
    scope_value: str
    expires_at: str | None


SCOPE_TYPES = frozenset({"directory", "domain", "command_class", "tool"})


class GrantStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    def add(self, scope_type: str, scope_value: str, expires_at: str | None = None) -> Grant:
        if scope_type not in SCOPE_TYPES:
            raise ValueError(f"unknown scope type {scope_type!r}")
        if scope_type == "directory":
            scope_value = os.path.realpath(scope_value)
        grant = Grant(new_id(), scope_type, scope_value, expires_at)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO permission_grants"
                " (id, scope_type, scope_value, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (grant.id, scope_type, scope_value, to_iso(self._clock.now()), expires_at),
            )
        return grant

    def revoke(self, grant_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE permission_grants SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (to_iso(self._clock.now()), grant_id),
            )
        return cur.rowcount == 1

    def active(self) -> list[Grant]:
        now = self._clock.now()
        rows = self._db.query(
            "SELECT id, scope_type, scope_value, expires_at FROM permission_grants"
            " WHERE revoked_at IS NULL"
        )
        return [
            Grant(r["id"], r["scope_type"], r["scope_value"], r["expires_at"])
            for r in rows
            if r["expires_at"] is None or from_iso(r["expires_at"]) > now
        ]


def _covers(grant: Grant, need: PermissionNeed) -> bool:
    if grant.scope_type != need.scope_type:
        return False
    if need.scope_type == "directory":
        target = Path(os.path.realpath(need.value))
        root = Path(grant.scope_value)
        return target == root or root in target.parents
    if need.scope_type == "domain":
        host = need.value.lower().rstrip(".")
        allowed = grant.scope_value.lower().rstrip(".")
        return host == allowed or host.endswith("." + allowed)
    return grant.scope_value == need.value


class PolicyEngine:
    def __init__(self, grants: GrantStore) -> None:
        self._grants = grants

    def evaluate(self, risk: Risk, needs: list[PermissionNeed]) -> PolicyDecision:
        active = self._grants.active()
        for need in needs:
            if not any(_covers(g, need) for g in active):
                return PolicyDecision(
                    Verdict.DENY, f"no active grant for {need.scope_type} {need.value!r}"
                )
        if risk in (Risk.CONSEQUENTIAL, Risk.HIGHEST):
            return PolicyDecision(Verdict.NEEDS_APPROVAL, f"{risk} actions require approval")
        return PolicyDecision(Verdict.ALLOW, "within granted scope")
