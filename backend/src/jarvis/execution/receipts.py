"""Execution receipts (BRIEF §4.10): built only from recorded facts, never from model claims."""

from __future__ import annotations

import json
from typing import Any

from jarvis.execution.states import ACTION_DONE_STATES, ActionState
from jarvis.execution.store import TaskStore

_STATE_LABELS = {
    ActionState.VERIFIED: "Verified",
    ActionState.UNVERIFIABLE: "Completed — no verification exists",
    ActionState.COMPLETED: "Completed, not verified",
    ActionState.USER_ATTESTED: "User-attested (not verified)",
    ActionState.UNCERTAIN: "Uncertain — outcome unknown",
}


def build_receipt(store: TaskStore, task_id: str) -> dict[str, Any]:
    task = store.task(task_id)
    if task is None:
        raise KeyError(task_id)
    actions = store.actions(task_id)
    entries: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for a in actions:
        intents = store.intents(a.id)
        details = (a.output or {}).get("receipt", {})
        files.extend(details.get("files", []))
        commands.extend(details.get("commands", []))
        for i in intents:
            if i["outcome"] in ("failed", "uncertain"):
                errors.append(
                    {
                        "action_id": a.id,
                        "attempt": i["attempt"],
                        "outcome": i["outcome"],
                        "detail": i["detail"],
                    }
                )
        entries.append(
            {
                "action_id": a.id,
                "tool": a.tool,
                "tool_version": a.tool_version,
                "parameters": a.params,
                "digest": a.digest,
                "state": a.state.value,
                "status_label": _STATE_LABELS.get(a.state, a.state.value.replace("_", " ").title()),
                "attempts": a.attempts,
                "approval_id": a.approval_id,
                "intents": intents,
                "verification": a.verification,
                "error": a.error,
            }
        )
    return {
        "task_id": task.id,
        "objective": task.objective,
        "plan": [
            {"step": n + 1, "tool": a.tool, "parameters": a.params} for n, a in enumerate(actions)
        ],
        "actions": entries,
        "tools_used": sorted({a.tool for a in actions}),
        "files": files,
        "commands": commands,
        "tests": [],
        "errors_and_recovery": errors,
        "final_status": task.state.value,
        "final_status_reason": task.state_reason,
        "verification_evidence": [
            {"action_id": a.id, **a.verification} for a in actions if a.verification
        ],
        "outstanding_actions": [
            {"action_id": a.id, "state": a.state.value}
            for a in actions
            if a.state not in ACTION_DONE_STATES
            and a.state not in (ActionState.REJECTED, ActionState.DENIED, ActionState.CANCELLED)
        ],
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


class ReceiptWriter:
    def __init__(self, store: TaskStore) -> None:
        self._store = store

    def write(self, task_id: str) -> dict[str, Any]:
        receipt = build_receipt(self._store, task_id)
        with self._store.db.transaction() as conn:
            conn.execute(
                "INSERT INTO receipts (task_id, receipt_json, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(task_id) DO UPDATE SET receipt_json = excluded.receipt_json,"
                " updated_at = excluded.updated_at",
                (task_id, json.dumps(receipt), self._store.now()),
            )
        return receipt

    def read(self, task_id: str) -> dict[str, Any] | None:
        rows = self._store.db.query(
            "SELECT receipt_json FROM receipts WHERE task_id = ?", (task_id,)
        )
        return json.loads(rows[0][0]) if rows else None
