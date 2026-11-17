"""The executor: the only way a tool runs (BRIEF §5.4, §5.5; ADR-0004, ADR-0005).

validate → policy → approval (if required) → write-ahead intent → execute with timeout →
outcome → verify → receipt + audit. Until the task engine (M7), every request is one
single-step task.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from jarvis.execution.digest import action_digest
from jarvis.execution.receipts import ReceiptWriter
from jarvis.execution.states import ActionState, TaskState
from jarvis.execution.store import ActionRow, TaskStore
from jarvis.tools.contract import (
    AnyTool,
    ExecContext,
    ReconcileOutcome,
    Recovery,
    VerificationStatus,
)
from jarvis.tools.registry import ToolRegistry
from jarvis.trust.approvals import ApprovalError, ApprovalService
from jarvis.trust.audit import AuditLog
from jarvis.trust.policy import PolicyEngine, Verdict


class ToolFailedError(Exception):
    """Raised by a tool when it knows for certain that its action did NOT happen."""


class ExecutionError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ExecutionResult:
    task_id: str
    action_id: str
    task_state: TaskState
    action_state: ActionState
    approval_id: str | None = None


# Errors after which we cannot know whether the side effect happened.
_UNCERTAIN_ERRORS: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError, OSError)


class Executor:
    def __init__(
        self,
        store: TaskStore,
        registry: ToolRegistry,
        policy: PolicyEngine,
        approvals: ApprovalService,
        audit: AuditLog,
        *,
        max_attempts: int = 3,
    ) -> None:
        self.store = store
        self.registry = registry
        self._policy = policy
        self._approvals = approvals
        self.audit = audit
        self.receipts = ReceiptWriter(store)
        self.max_attempts = max_attempts

    # -- entry point --------------------------------------------------------------------------
    async def submit(
        self, tool_name: str, params: dict[str, Any], objective: str, actor: str = "user"
    ) -> ExecutionResult:
        tool = self.registry.get(tool_name)
        if tool is None:
            raise ExecutionError("unknown_tool", f"no tool named {tool_name!r}", 404)
        inp = self._validate(tool, params)
        canonical = inp.model_dump(mode="json")
        digest = action_digest(tool.name, tool.version, canonical)
        with self.store.db.transaction() as conn:
            task_id, action_id = self.store.create(
                conn,
                objective=objective,
                tool=tool.name,
                tool_version=tool.version,
                params=canonical,
                digest=digest,
                risk=tool.risk.value,
                category=tool.category.value if tool.category else None,
                recovery=tool.recovery.value if tool.recovery else None,
                actor=actor,
            )
            self.store.set_task(conn, task_id, TaskState.RUNNING)
        decision = self._policy.evaluate(tool.risk, tool.permissions(inp))
        if decision.verdict is Verdict.DENY:
            with self.store.db.transaction() as conn:
                self.store.set_action(conn, action_id, ActionState.DENIED, error=decision.reason)
                self.audit.append(
                    "policy.denied",
                    {"action_id": action_id, "reason": decision.reason},
                    task_id=task_id,
                    conn=conn,
                )
                self.store.set_task(conn, task_id, TaskState.FAILED, decision.reason)
            return self._finish(task_id, action_id)
        if decision.verdict is Verdict.NEEDS_APPROVAL:
            return self._request_approval(task_id, action_id, tool, inp)
        return await self.run(action_id, None)

    def _validate(self, tool: AnyTool, params: dict[str, Any]) -> BaseModel:
        try:
            return tool.input_model.model_validate(params)
        except ValidationError:
            raise ExecutionError(
                "invalid_input", f"input does not match {tool.name}'s schema", 422
            ) from None

    def _request_approval(
        self, task_id: str, action_id: str, tool: AnyTool, inp: BaseModel, retry: bool = False
    ) -> ExecutionResult:
        action = self._action(action_id)
        with self.store.db.transaction() as conn:
            approval = self._approvals.request(
                conn,
                action_id=action_id,
                task_id=task_id,
                digest=action.digest,
                category=tool.category,
                text=tool.describe(inp),
                params=action.params,
            )
            self.store.set_action(
                conn, action_id, ActionState.WAITING_FOR_APPROVAL, approval_id=approval.id
            )
            reason = "retry needs approval" if retry else "approval required"
            self.store.set_task(conn, task_id, TaskState.WAITING_FOR_APPROVAL, reason)
        return self._finish(task_id, action_id, approval.id)

    # -- approval decisions --------------------------------------------------------------------
    async def decide(
        self, approval_id: str, approve: bool, native_confirmation: str | None
    ) -> ExecutionResult:
        approval = self._approvals.get(approval_id)
        task_id = self._action(approval.action_id).task_id if approval else None
        self._approvals.decide(approval_id, approve, native_confirmation, task_id)
        assert approval is not None  # decide() raised otherwise
        action = self._action(approval.action_id)
        if not approve:
            with self.store.db.transaction() as conn:
                self.store.set_action(
                    conn, action.id, ActionState.REJECTED, error="approval rejected by the user"
                )
                self.store.set_task(conn, action.task_id, TaskState.CANCELLED, "approval rejected")
            return self._finish(action.task_id, action.id)
        with self.store.db.transaction() as conn:
            self.store.set_task(conn, action.task_id, TaskState.RUNNING)
        return await self.run(action.id, approval_id)

    # -- running ---------------------------------------------------------------------------
    async def run(self, action_id: str, approval_id: str | None) -> ExecutionResult:
        action = self._action(action_id)
        tool = self._tool(action)
        inp = tool.input_model.model_validate(action.params)
        attempt = action.attempts + 1
        # Recompute from what will actually run: a stored digest is not evidence.
        digest = action_digest(tool.name, tool.version, inp.model_dump(mode="json"))
        try:
            with self.store.db.transaction() as conn:
                if approval_id is not None:
                    self._approvals.consume(conn, approval_id, digest)
                elif digest != action.digest:
                    raise ApprovalError("action_tampered", "action changed after planning", "")
                intent_id = self.store.record_intent(conn, action, attempt)
                self.store.set_action(conn, action_id, ActionState.ATTEMPTED, attempts=attempt)
                self.audit.append(
                    "action.intent_recorded",
                    {
                        "action_id": action_id,
                        "attempt": attempt,
                        "idempotency_key": action.idempotency_key,
                    },
                    task_id=action.task_id,
                    conn=conn,
                )
        except ApprovalError as err:
            self._approvals.audit_refusal(err, action.task_id)
            raise ExecutionError(err.code, str(err), 403) from None
        ctx = ExecContext(action_id, action.idempotency_key, attempt)
        try:
            out = await asyncio.wait_for(tool.execute(inp, ctx), tool.timeout_s)
        except ToolFailedError as exc:
            return await self._failed(action, intent_id, str(exc), tool)
        except _UNCERTAIN_ERRORS as exc:
            if tool.idempotent:
                return await self._failed(action, intent_id, _describe(exc), tool)
            return await self._uncertain(action, intent_id, _describe(exc), tool)
        except Exception as exc:
            if tool.side_effects:
                return await self._uncertain(action, intent_id, _describe(exc), tool)
            return await self._failed(action, intent_id, _describe(exc), tool)
        output = out.model_dump(mode="json")
        with self.store.db.transaction() as conn:
            self.store.record_outcome(conn, intent_id, action_id, "completed", {"output": output})
            self.store.set_action(conn, action_id, ActionState.COMPLETED, output_json=output)
            self.audit.append(
                "action.completed", {"action_id": action_id}, task_id=action.task_id, conn=conn
            )
        return await self._verify(action_id, tool, inp, out, ctx)

    async def _verify(
        self, action_id: str, tool: AnyTool, inp: BaseModel, out: BaseModel, ctx: ExecContext
    ) -> ExecutionResult:
        action = self._action(action_id)
        try:
            v = await asyncio.wait_for(tool.verify(inp, out, ctx), tool.timeout_s)
            status, evidence = v.status, v.evidence
        except Exception as exc:
            status, evidence = VerificationStatus.FAILED, {"error": _describe(exc)}
        record = {"status": status.value, "evidence": evidence}
        with self.store.db.transaction() as conn:
            if status is VerificationStatus.VERIFIED:
                self.store.set_action(
                    conn, action_id, ActionState.VERIFIED, verification_json=record
                )
                self.audit.append(
                    "action.verified",
                    {"action_id": action_id, **record},
                    task_id=action.task_id,
                    conn=conn,
                )
                self.store.set_task(conn, action.task_id, TaskState.COMPLETED)
            elif status is VerificationStatus.UNVERIFIABLE:
                self.store.set_action(
                    conn, action_id, ActionState.UNVERIFIABLE, verification_json=record
                )
                self.audit.append(
                    "action.unverifiable",
                    {"action_id": action_id},
                    task_id=action.task_id,
                    conn=conn,
                )
                self.store.set_task(
                    conn,
                    action.task_id,
                    TaskState.COMPLETED,
                    "completed; no verification exists for this action",
                )
            else:  # "Completed, not verified": never reported as verified
                self.store.set_action(
                    conn, action_id, ActionState.COMPLETED, verification_json=record
                )
                self.audit.append(
                    "action.verification_failed",
                    {"action_id": action_id, **record},
                    task_id=action.task_id,
                    conn=conn,
                )
                self.store.set_task(
                    conn,
                    action.task_id,
                    TaskState.NEEDS_REVIEW,
                    "completed, not verified: the independent check failed",
                )
        return self._finish(action.task_id, action_id)

    async def _failed(
        self, action: ActionRow, intent_id: str, error: str, tool: AnyTool
    ) -> ExecutionResult:
        with self.store.db.transaction() as conn:
            self.store.record_outcome(conn, intent_id, action.id, "failed", {"error": error})
            self.store.set_action(conn, action.id, ActionState.FAILED, error=error)
            self.audit.append(
                "action.failed",
                {"action_id": action.id, "error": error},
                task_id=action.task_id,
                conn=conn,
            )
        current = self._action(action.id)
        if tool.idempotent and current.attempts < self.max_attempts:
            return await self.run(action.id, None)  # retries only for idempotent tools
        with self.store.db.transaction() as conn:
            self.store.set_task(conn, action.task_id, TaskState.FAILED, error)
        return self._finish(action.task_id, action.id)

    async def _uncertain(
        self, action: ActionRow, intent_id: str, error: str, tool: AnyTool
    ) -> ExecutionResult:
        with self.store.db.transaction() as conn:
            self.store.record_outcome(conn, intent_id, action.id, "uncertain", {"error": error})
            self.store.set_action(conn, action.id, ActionState.UNCERTAIN, error=error)
            self.audit.append(
                "action.uncertain",
                {"action_id": action.id, "error": error},
                task_id=action.task_id,
                conn=conn,
            )
        return await self.resolve_uncertain(action.id)

    # -- uncertain actions (also used by startup recovery) -----------------------------------
    async def resolve_uncertain(self, action_id: str) -> ExecutionResult:
        action = self._action(action_id)
        tool = self._tool(action)
        inp = tool.input_model.model_validate(action.params)
        if tool.recovery is Recovery.IDEMPOTENT and action.attempts < self.max_attempts:
            return await self.run(action_id, None)  # same idempotency key
        if tool.recovery is Recovery.RECONCILABLE:
            ctx = ExecContext(action.id, action.idempotency_key, action.attempts)
            evidence: dict[str, Any]
            try:
                rec = await asyncio.wait_for(tool.reconcile(inp, ctx), tool.timeout_s)
                outcome, evidence = rec.outcome, rec.evidence
            except Exception as exc:
                outcome, evidence = ReconcileOutcome.INCONCLUSIVE, {"error": _describe(exc)}
            self.audit.append(
                "action.reconciled",
                {"action_id": action_id, "outcome": outcome.value, "evidence": evidence},
                task_id=action.task_id,
            )
            if outcome is ReconcileOutcome.HAPPENED:
                with self.store.db.transaction() as conn:
                    self.store.set_action(
                        conn, action_id, ActionState.COMPLETED, output_json={"reconciled": evidence}
                    )
                out = tool.output_model.model_validate(evidence.get("output") or {})
                return await self._verify(action_id, tool, inp, out, ctx)
            if outcome is ReconcileOutcome.NOT_HAPPENED:
                if tool.risk.value in ("consequential", "highest"):
                    return self._request_approval(action.task_id, action_id, tool, inp, True)
                if action.attempts < self.max_attempts:
                    return await self.run(action_id, None)
        with self.store.db.transaction() as conn:
            self.store.set_task(
                conn, action.task_id, TaskState.NEEDS_REVIEW, "the outcome of an action is unknown"
            )
        return self._finish(action.task_id, action_id)

    async def resolve_review(self, action_id: str, choice: str) -> ExecutionResult:
        """The user's answer in Needs review: happened | retry | cancel."""
        action = self._action(action_id)
        task = self.store.task(action.task_id)
        reviewable = action.state in (ActionState.UNCERTAIN, ActionState.COMPLETED)
        if task is None or task.state is not TaskState.NEEDS_REVIEW or not reviewable:
            raise ExecutionError("not_reviewable", "this action is not waiting for review", 409)
        if choice == "happened":
            with self.store.db.transaction() as conn:
                self.store.set_action(conn, action_id, ActionState.USER_ATTESTED)
                self.audit.append(
                    "action.user_attested",
                    {"action_id": action_id},
                    actor="user",
                    task_id=action.task_id,
                    conn=conn,
                )
                self.store.set_task(
                    conn,
                    action.task_id,
                    TaskState.COMPLETED,
                    "user attested the action happened (not verified)",
                )
            return self._finish(action.task_id, action_id)
        if choice == "retry":
            tool = self._tool(action)
            inp = tool.input_model.model_validate(action.params)
            return self._request_approval(action.task_id, action_id, tool, inp, retry=True)
        if choice == "cancel":
            with self.store.db.transaction() as conn:
                self.store.set_action(conn, action_id, ActionState.CANCELLED)
                self.store.set_task(
                    conn, action.task_id, TaskState.CANCELLED, "cancelled by the user during review"
                )
            return self._finish(action.task_id, action_id)
        raise ExecutionError("invalid_choice", "choice must be happened, retry or cancel", 422)

    # -- helpers ---------------------------------------------------------------------------
    def _action(self, action_id: str) -> ActionRow:
        action = self.store.action(action_id)
        if action is None:
            raise ExecutionError("unknown_action", "no such action", 404)
        return action

    def _tool(self, action: ActionRow) -> AnyTool:
        tool = self.registry.get(action.tool)
        if tool is None:
            raise ExecutionError("tool_unavailable", f"tool {action.tool!r} is not available", 409)
        return tool

    def _finish(
        self, task_id: str, action_id: str, approval_id: str | None = None
    ) -> ExecutionResult:
        self.receipts.write(task_id)
        task = self.store.task(task_id)
        action = self._action(action_id)
        assert task is not None
        return ExecutionResult(task_id, action_id, task.state, action.state, approval_id)


def _describe(exc: BaseException) -> str:
    text = str(exc)
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
