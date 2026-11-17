"""Exhaustive transition-table tests (BRIEF §4.9: 'The transition table is tested exhaustively')."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from jarvis.execution.states import (
    ACTION_TRANSITIONS,
    TASK_TRANSITIONS,
    TERMINAL_TASK_STATES,
    ActionState,
    InvalidTransitionError,
    TaskState,
    check_action_transition,
    check_task_transition,
)
from jarvis.ids import new_id
from tests.support.kernel import kernel


@pytest.mark.parametrize(("src", "dst"), list(itertools.product(TaskState, TaskState)))
def test_every_task_transition(src: TaskState, dst: TaskState) -> None:
    if dst in TASK_TRANSITIONS[src]:
        check_task_transition(src, dst)
    else:
        with pytest.raises(InvalidTransitionError):
            check_task_transition(src, dst)


@pytest.mark.parametrize(("src", "dst"), list(itertools.product(ActionState, ActionState)))
def test_every_action_transition(src: ActionState, dst: ActionState) -> None:
    if dst in ACTION_TRANSITIONS[src]:
        check_action_transition(src, dst)
    else:
        with pytest.raises(InvalidTransitionError):
            check_action_transition(src, dst)


def test_tables_cover_every_state_and_terminals_are_final() -> None:
    assert set(TASK_TRANSITIONS) == set(TaskState)
    assert set(ACTION_TRANSITIONS) == set(ActionState)
    for t in TERMINAL_TASK_STATES:
        assert TASK_TRANSITIONS[t] == frozenset()
    # Verified can only be reached from Completed (a tool's own success claim comes first).
    sources = {s for s, targets in ACTION_TRANSITIONS.items() if ActionState.VERIFIED in targets}
    assert sources == {ActionState.COMPLETED}
    # User-attested is never a path to Verified.
    assert ActionState.VERIFIED not in ACTION_TRANSITIONS[ActionState.USER_ATTESTED]


@pytest.mark.parametrize(
    "action_state",
    [
        s
        for s in ActionState
        if s not in (ActionState.VERIFIED, ActionState.UNVERIFIABLE, ActionState.USER_ATTESTED)
    ],
)
def test_task_cannot_complete_unless_every_action_is_done(
    tmp_path: Path, action_state: ActionState
) -> None:
    with kernel(tmp_path) as (s, _clock):
        with s.db.transaction() as conn:
            task_id, action_id = s.store.create(
                conn,
                objective="t",
                tool="fixture.echo",
                tool_version=1,
                params={},
                digest="d",
                risk="low",
                category=None,
                recovery=None,
                actor="test",
            )
            s.store.set_task(conn, task_id, TaskState.RUNNING)
            conn.execute(
                "UPDATE actions SET state = ? WHERE id = ?", (action_state.value, action_id)
            )
        with pytest.raises(InvalidTransitionError), s.db.transaction() as conn:
            s.store.set_task(conn, task_id, TaskState.COMPLETED)
        assert s.store.task(task_id).state is TaskState.RUNNING  # type: ignore[union-attr]


@pytest.mark.parametrize("target", [TaskState.COMPLETED, TaskState.FAILED])
@pytest.mark.parametrize("blocking", [ActionState.UNCERTAIN, ActionState.ATTEMPTED])
def test_task_cannot_finish_while_an_action_is_uncertain(
    tmp_path: Path, target: TaskState, blocking: ActionState
) -> None:
    with kernel(tmp_path) as (s, _clock):
        with s.db.transaction() as conn:
            task_id, done = s.store.create(
                conn,
                objective="t",
                tool="fixture.echo",
                tool_version=1,
                params={},
                digest="d",
                risk="low",
                category=None,
                recovery=None,
                actor="test",
            )
            s.store.set_task(conn, task_id, TaskState.RUNNING)
            conn.execute("UPDATE actions SET state = 'verified' WHERE id = ?", (done,))
            other = new_id()
            conn.execute(
                "INSERT INTO actions (id, task_id, tool, tool_version, params_json, digest,"
                " idempotency_key, risk, state, created_at, updated_at)"
                " VALUES (?, ?, 'fixture.echo', 1, '{}', 'd', 'k', 'low', ?, 'x', 'x')",
                (other, task_id, blocking.value),
            )
        with pytest.raises(InvalidTransitionError), s.db.transaction() as conn:
            s.store.set_task(conn, task_id, target)
