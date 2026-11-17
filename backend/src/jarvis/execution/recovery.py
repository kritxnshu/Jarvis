"""Startup recovery (BRIEF §4.9 restart rule, §5.5).

Tasks found Running become Paused ("interrupted"). Intents without an outcome become Uncertain
and are resolved by the tool's declared strategy. Nothing is re-executed blindly.
"""

from __future__ import annotations

import logging

from jarvis.execution.executor import Executor
from jarvis.execution.states import ActionState, TaskState

log = logging.getLogger("jarvis.execution.recovery")

NO_OUTCOME = "no outcome was recorded before the backend stopped"


async def recover(executor: Executor) -> dict[str, int]:
    store = executor.store
    interrupted = store.tasks(TaskState.RUNNING, limit=100_000)
    open_intents = store.open_intents()
    if not interrupted and not open_intents:
        return {"interrupted_tasks": 0, "uncertain_actions": 0}
    executor_audit = executor.audit
    executor_audit.append(
        "recovery.started",
        {"interrupted_tasks": len(interrupted), "open_intents": len(open_intents)},
    )
    with store.db.transaction() as conn:
        for task in interrupted:
            store.set_task(conn, task.id, TaskState.PAUSED, "interrupted")
        for intent_id, action_id in open_intents:
            action = store.action(action_id)
            assert action is not None
            store.record_outcome(conn, intent_id, action_id, "uncertain", {"error": NO_OUTCOME})
            store.set_action(conn, action_id, ActionState.UNCERTAIN, error=NO_OUTCOME)
            executor_audit.append(
                "action.uncertain",
                {"action_id": action_id, "error": NO_OUTCOME},
                task_id=action.task_id,
                conn=conn,
            )

    for action in store.actions_in(ActionState.UNCERTAIN):
        task = store.task(action.task_id)
        if task is None or task.state is not TaskState.PAUSED:
            continue  # already waiting for the user
        with store.db.transaction() as conn:
            store.set_task(conn, task.id, TaskState.RUNNING, "recovering after restart")
        result = await executor.resolve_uncertain(action.id)
        log.info(
            "recovered action",
            extra={
                "action_id": action.id,
                "state": result.action_state.value,
                "task_state": result.task_state.value,
            },
        )

    # Interrupted before any intent was written: the action never started.
    for task in store.tasks(TaskState.PAUSED, limit=100_000):
        if task.state_reason != "interrupted":
            continue
        with store.db.transaction() as conn:
            for action in store.actions(task.id):
                if action.state is ActionState.PLANNED:
                    store.set_action(
                        conn,
                        action.id,
                        ActionState.CANCELLED,
                        error="interrupted before it started",
                    )
            store.set_task(conn, task.id, TaskState.CANCELLED, "interrupted before it started")
        executor.receipts.write(task.id)
    return {"interrupted_tasks": len(interrupted), "uncertain_actions": len(open_intents)}
