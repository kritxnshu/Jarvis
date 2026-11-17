"""Task and action state machines with explicit, tested transition tables (BRIEF §4.9, §4.10)."""

from __future__ import annotations

from enum import StrEnum


class TaskState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    NEEDS_REVIEW = "needs_review"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_TASK_STATES = frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED})

T = TaskState
TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    T.PENDING: frozenset({T.RUNNING, T.CANCELLED}),
    T.RUNNING: frozenset(
        {T.WAITING_FOR_APPROVAL, T.NEEDS_REVIEW, T.PAUSED, T.COMPLETED, T.FAILED, T.CANCELLED}
    ),
    T.WAITING_FOR_APPROVAL: frozenset({T.RUNNING, T.CANCELLED, T.PAUSED}),
    T.NEEDS_REVIEW: frozenset({T.RUNNING, T.WAITING_FOR_APPROVAL, T.COMPLETED, T.CANCELLED}),
    T.PAUSED: frozenset({T.RUNNING, T.NEEDS_REVIEW, T.CANCELLED}),
    T.COMPLETED: frozenset(),
    T.FAILED: frozenset(),
    T.CANCELLED: frozenset(),
}


class ActionState(StrEnum):
    PLANNED = "planned"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    ATTEMPTED = "attempted"  # intent recorded, tool running
    COMPLETED = "completed"  # tool reported success, not (yet) independently verified
    VERIFIED = "verified"  # independent check passed
    UNVERIFIABLE = "unverifiable"  # completed; no check exists, said explicitly
    FAILED = "failed"
    UNCERTAIN = "uncertain"  # outcome unknown (crash, non-idempotent timeout)
    USER_ATTESTED = "user_attested"  # user said "it happened"; never Verified
    REJECTED = "rejected"  # approval rejected or expired; never ran
    DENIED = "denied"  # policy refused; never ran
    CANCELLED = "cancelled"


A = ActionState
ACTION_TRANSITIONS: dict[ActionState, frozenset[ActionState]] = {
    A.PLANNED: frozenset({A.WAITING_FOR_APPROVAL, A.ATTEMPTED, A.DENIED, A.CANCELLED}),
    A.WAITING_FOR_APPROVAL: frozenset({A.ATTEMPTED, A.REJECTED, A.CANCELLED}),
    A.ATTEMPTED: frozenset({A.COMPLETED, A.FAILED, A.UNCERTAIN}),
    # COMPLETED whose verification failed ("completed, not verified") goes to Needs review.
    A.COMPLETED: frozenset(
        {A.VERIFIED, A.UNVERIFIABLE, A.USER_ATTESTED, A.WAITING_FOR_APPROVAL, A.CANCELLED}
    ),
    A.UNCERTAIN: frozenset(
        {A.ATTEMPTED, A.COMPLETED, A.USER_ATTESTED, A.WAITING_FOR_APPROVAL, A.CANCELLED}
    ),
    A.FAILED: frozenset({A.ATTEMPTED}),  # bounded retry
    A.VERIFIED: frozenset(),
    A.UNVERIFIABLE: frozenset(),
    A.USER_ATTESTED: frozenset(),
    A.REJECTED: frozenset(),
    A.DENIED: frozenset(),
    A.CANCELLED: frozenset(),
}

# A task may only complete when every action ended in one of these.
ACTION_DONE_STATES = frozenset({A.VERIFIED, A.UNVERIFIABLE, A.USER_ATTESTED})
# While any action is in one of these, its task can be neither Completed nor Failed.
ACTION_BLOCKING_STATES = frozenset({A.UNCERTAIN, A.ATTEMPTED})


class InvalidTransitionError(ValueError):
    pass


def check_task_transition(current: TaskState, target: TaskState) -> None:
    if target not in TASK_TRANSITIONS[current]:
        raise InvalidTransitionError(f"task {current} -> {target} is not allowed")


def check_action_transition(current: ActionState, target: ActionState) -> None:
    if target not in ACTION_TRANSITIONS[current]:
        raise InvalidTransitionError(f"action {current} -> {target} is not allowed")
