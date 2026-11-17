"""Durable tasks and actions. Every state change goes through the transition tables here."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from jarvis.clock import Clock, SystemClock, to_iso
from jarvis.execution.states import (
    ACTION_BLOCKING_STATES,
    ACTION_DONE_STATES,
    ActionState,
    InvalidTransitionError,
    TaskState,
    check_action_transition,
    check_task_transition,
)
from jarvis.ids import new_id
from jarvis.storage.db import Database
from jarvis.trust.audit import AuditLog
from jarvis.trust.redaction import Redactor


@dataclass(frozen=True)
class TaskRow:
    id: str
    objective: str
    state: TaskState
    state_reason: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ActionRow:
    id: str
    task_id: str
    tool: str
    tool_version: int
    params: dict[str, Any]
    digest: str
    idempotency_key: str
    risk: str
    category: str | None
    recovery: str | None
    state: ActionState
    attempts: int
    approval_id: str | None
    output: dict[str, Any] | None
    error: str | None
    verification: dict[str, Any] | None
    created_at: str
    updated_at: str


def _task(r: sqlite3.Row) -> TaskRow:
    return TaskRow(
        r["id"],
        r["objective"],
        TaskState(r["state"]),
        r["state_reason"],
        r["created_at"],
        r["updated_at"],
    )


def _action(r: sqlite3.Row) -> ActionRow:
    def load(text: str | None) -> dict[str, Any] | None:
        return json.loads(text) if text else None

    return ActionRow(
        id=r["id"],
        task_id=r["task_id"],
        tool=r["tool"],
        tool_version=int(r["tool_version"]),
        params=json.loads(r["params_json"]),
        digest=r["digest"],
        idempotency_key=r["idempotency_key"],
        risk=r["risk"],
        category=r["category"],
        recovery=r["recovery"],
        state=ActionState(r["state"]),
        attempts=int(r["attempts"]),
        approval_id=r["approval_id"],
        output=load(r["output_json"]),
        error=r["error"],
        verification=load(r["verification_json"]),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class TaskStore:
    def __init__(
        self, db: Database, audit: AuditLog, redactor: Redactor, clock: Clock | None = None
    ) -> None:
        self.db = db
        self._audit = audit
        self._redactor = redactor
        self._clock = clock or SystemClock()

    def now(self) -> str:
        return to_iso(self._clock.now())

    # -- creation -------------------------------------------------------------------------
    def create(
        self,
        conn: sqlite3.Connection,
        *,
        objective: str,
        tool: str,
        tool_version: int,
        params: dict[str, Any],
        digest: str,
        risk: str,
        category: str | None,
        recovery: str | None,
        actor: str,
    ) -> tuple[str, str]:
        now = self.now()
        task_id, action_id = new_id(), new_id()
        conn.execute(
            "INSERT INTO tasks (id, objective, state, created_at, updated_at) VALUES (?,?,?,?,?)",
            (task_id, self._redactor.redact(objective), TaskState.PENDING.value, now, now),
        )
        conn.execute(
            "INSERT INTO actions (id, task_id, tool, tool_version, params_json, digest,"
            " idempotency_key, risk, category, recovery, state, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                action_id,
                task_id,
                tool,
                tool_version,
                json.dumps(self._redactor.redact_value(params)),
                digest,
                new_id(),
                risk,
                category,
                recovery,
                ActionState.PLANNED.value,
                now,
                now,
            ),
        )
        self._audit.append(
            "task.created", {"objective": objective}, actor=actor, task_id=task_id, conn=conn
        )
        self._audit.append(
            "action.planned",
            {"action_id": action_id, "tool": tool, "digest": digest, "params": params},
            actor=actor,
            task_id=task_id,
            conn=conn,
        )
        return task_id, action_id

    # -- reads ----------------------------------------------------------------------------
    def task(self, task_id: str) -> TaskRow | None:
        rows = self.db.query("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return _task(rows[0]) if rows else None

    def tasks(self, state: TaskState | None = None, limit: int = 100) -> list[TaskRow]:
        if state is None:
            rows = self.db.query("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        else:
            rows = self.db.query(
                "SELECT * FROM tasks WHERE state = ? ORDER BY created_at DESC LIMIT ?",
                (state.value, limit),
            )
        return [_task(r) for r in rows]

    def action(self, action_id: str) -> ActionRow | None:
        rows = self.db.query("SELECT * FROM actions WHERE id = ?", (action_id,))
        return _action(rows[0]) if rows else None

    def actions(self, task_id: str) -> list[ActionRow]:
        rows = self.db.query(
            "SELECT * FROM actions WHERE task_id = ? ORDER BY created_at", (task_id,)
        )
        return [_action(r) for r in rows]

    def actions_in(self, state: ActionState) -> list[ActionRow]:
        rows = self.db.query("SELECT * FROM actions WHERE state = ?", (state.value,))
        return [_action(r) for r in rows]

    # -- transitions ----------------------------------------------------------------------
    def set_action(
        self, conn: sqlite3.Connection, action_id: str, target: ActionState, **fields: Any
    ) -> None:
        row = conn.execute("SELECT state FROM actions WHERE id = ?", (action_id,)).fetchone()
        if ActionState(row["state"]) is not target:  # same state: only the fields change
            check_action_transition(ActionState(row["state"]), target)
        sets = ["state = ?", "updated_at = ?"]
        values: list[Any] = [target.value, self.now()]
        for column, value in fields.items():
            if column not in {
                "attempts",
                "approval_id",
                "output_json",
                "error",
                "verification_json",
            }:
                raise ValueError(f"cannot set column {column}")
            if column in {"output_json", "verification_json"} and value is not None:
                value = json.dumps(self._redactor.redact_value(value))
            if column == "error" and value is not None:
                value = self._redactor.redact(str(value))
            sets.append(f"{column} = ?")
            values.append(value)
        values.append(action_id)
        conn.execute(f"UPDATE actions SET {', '.join(sets)} WHERE id = ?", values)  # noqa: S608

    def set_task(
        self, conn: sqlite3.Connection, task_id: str, target: TaskState, reason: str | None = None
    ) -> None:
        row = conn.execute("SELECT state FROM tasks WHERE id = ?", (task_id,)).fetchone()
        current = TaskState(row["state"])
        if current is target:
            conn.execute(
                "UPDATE tasks SET state_reason = ?, updated_at = ? WHERE id = ?",
                (reason, self.now(), task_id),
            )
            return
        check_task_transition(current, target)
        states = [
            ActionState(r["state"])
            for r in conn.execute(
                "SELECT state FROM actions WHERE task_id = ?", (task_id,)
            ).fetchall()
        ]
        if target in (TaskState.COMPLETED, TaskState.FAILED) and any(
            s in ACTION_BLOCKING_STATES for s in states
        ):
            raise InvalidTransitionError(f"task cannot be {target} while an action is uncertain")
        if target is TaskState.COMPLETED and not all(s in ACTION_DONE_STATES for s in states):
            raise InvalidTransitionError("task cannot be completed before all its actions are done")
        conn.execute(
            "UPDATE tasks SET state = ?, state_reason = ?, updated_at = ? WHERE id = ?",
            (target.value, reason, self.now(), task_id),
        )
        self._audit.append(
            "task.state_changed",
            {"from": current.value, "to": target.value, "reason": reason},
            task_id=task_id,
            conn=conn,
        )

    # -- intents --------------------------------------------------------------------------
    def record_intent(self, conn: sqlite3.Connection, action: ActionRow, attempt: int) -> str:
        intent_id = new_id()
        conn.execute(
            "INSERT INTO action_intents (id, action_id, attempt, digest, idempotency_key,"
            " started_at) VALUES (?,?,?,?,?,?)",
            (intent_id, action.id, attempt, action.digest, action.idempotency_key, self.now()),
        )
        return intent_id

    def record_outcome(
        self,
        conn: sqlite3.Connection,
        intent_id: str,
        action_id: str,
        outcome: str,
        detail: dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO action_outcomes (intent_id, action_id, outcome, detail_json, finished_at)"
            " VALUES (?,?,?,?,?)",
            (
                intent_id,
                action_id,
                outcome,
                json.dumps(self._redactor.redact_value(detail)),
                self.now(),
            ),
        )

    def open_intents(self) -> list[tuple[str, str]]:
        """(intent_id, action_id) for intents that never got an outcome (crash mid-action)."""
        rows = self.db.query(
            "SELECT i.id, i.action_id FROM action_intents i"
            " LEFT JOIN action_outcomes o ON o.intent_id = i.id WHERE o.intent_id IS NULL"
        )
        return [(str(r[0]), str(r[1])) for r in rows]

    def intents(self, action_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT i.id, i.attempt, i.idempotency_key, i.started_at, o.outcome, o.detail_json,"
            " o.finished_at FROM action_intents i LEFT JOIN action_outcomes o"
            " ON o.intent_id = i.id WHERE i.action_id = ? ORDER BY i.attempt",
            (action_id,),
        )
        return [
            {
                "intent_id": r[0],
                "attempt": r[1],
                "idempotency_key": r[2],
                "started_at": r[3],
                "outcome": r[4],
                "detail": json.loads(r[5]) if r[5] else None,
                "finished_at": r[6],
            }
            for r in rows
        ]
