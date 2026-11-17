"""Routes for tasks, approvals, review, audit and permission grants (M2)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from jarvis.api.schemas import (
    ApprovalList,
    ApprovalView,
    AuditEntries,
    AuditEntryView,
    ChainVerificationView,
    ExecutionView,
    GrantList,
    GrantView,
    Receipt,
    TaskDetail,
    TaskList,
    TaskView,
)
from jarvis.events import EventEnvelope
from jarvis.execution.executor import ExecutionError, ExecutionResult
from jarvis.execution.receipts import build_receipt
from jarvis.execution.states import TaskState
from jarvis.services import Services
from jarvis.trust.approvals import Approval, ApprovalError
from jarvis.trust.policy import SCOPE_TYPES


class TaskSubmit(BaseModel):
    tool: str = Field(min_length=1, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict[str, Any])
    objective: str = Field(min_length=1, max_length=2000)


class ReviewDecision(BaseModel):
    action_id: str
    choice: Literal["happened", "retry", "cancel"]


class ApprovalDecision(BaseModel):
    approve: bool
    native_confirmation: str | None = Field(default=None, max_length=128)


class AuditSearch(BaseModel):
    type_prefix: str | None = Field(default=None, max_length=64)
    task_id: str | None = Field(default=None, max_length=64)
    text: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=200, ge=1, le=1000)
    before_seq: int | None = None


class GrantCreate(BaseModel):
    scope_type: str
    scope_value: str = Field(min_length=1, max_length=4096)
    expires_at: str | None = None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _approval_view(a: Approval) -> ApprovalView:
    view = asdict(a)
    view["status"] = a.status.value
    return ApprovalView.model_validate(view)


def build_trust_router(s: Services) -> APIRouter:
    router = APIRouter(prefix="/v1")

    def result_view(r: ExecutionResult) -> ExecutionView:
        s.bus.publish(
            EventEnvelope(
                type="task.updated", task_id=r.task_id, payload={"state": r.task_state.value}
            )
        )
        return ExecutionView(
            task_id=r.task_id,
            action_id=r.action_id,
            task_state=r.task_state.value,
            action_state=r.action_state.value,
            approval_id=r.approval_id,
            receipt=Receipt.model_validate(build_receipt(s.store, r.task_id)),
        )

    @router.post("/tasks")
    async def submit(body: TaskSubmit) -> Any:
        try:
            return result_view(await s.executor.submit(body.tool, body.params, body.objective))
        except ExecutionError as e:
            return _error(e.status, e.code, str(e))

    @router.get("/tasks")
    def list_tasks(state: str | None = None) -> Any:
        try:
            wanted = TaskState(state) if state else None
        except ValueError:
            return _error(422, "invalid_state", "unknown task state")
        return TaskList(tasks=[TaskView.model_validate(asdict(t)) for t in s.store.tasks(wanted)])

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str) -> Any:
        task = s.store.task(task_id)
        if task is None:
            return _error(404, "unknown_task", "no such task")
        return TaskDetail(
            task=TaskView.model_validate(asdict(task)),
            receipt=Receipt.model_validate(build_receipt(s.store, task_id)),
        )

    @router.post("/tasks/{task_id}/review")
    async def review(task_id: str, body: ReviewDecision) -> Any:
        action = s.store.action(body.action_id)
        if action is None or action.task_id != task_id:
            return _error(404, "unknown_action", "no such action in this task")
        try:
            return result_view(await s.executor.resolve_review(body.action_id, body.choice))
        except ExecutionError as e:
            return _error(e.status, e.code, str(e))

    @router.get("/approvals")
    def pending() -> Any:
        return ApprovalList(approvals=[_approval_view(a) for a in s.approvals.pending()])

    @router.get("/approvals/{approval_id}")
    def get_approval(approval_id: str) -> Any:
        a = s.approvals.get(approval_id)
        return _approval_view(a) if a else _error(404, "approval_not_found", "no such approval")

    @router.post("/approvals/{approval_id}/decision")
    async def decide(approval_id: str, body: ApprovalDecision) -> Any:
        try:
            r = await s.executor.decide(approval_id, body.approve, body.native_confirmation)
        except ApprovalError as e:
            status = 404 if e.code == "approval_not_found" else 403
            return _error(status, e.code, str(e))
        except ExecutionError as e:
            return _error(e.status, e.code, str(e))
        return result_view(r)

    @router.post("/audit/search")
    def audit_search(body: AuditSearch) -> Any:
        entries = s.audit.list(
            type_prefix=body.type_prefix,
            task_id=body.task_id,
            text=body.text,
            limit=body.limit,
            before_seq=body.before_seq,
        )
        return AuditEntries(entries=[AuditEntryView.model_validate(asdict(e)) for e in entries])

    @router.get("/audit/verify")
    def audit_verify() -> Any:
        return ChainVerificationView.model_validate(asdict(s.audit.verify()))

    @router.get("/audit/export/{fmt}")
    def audit_export(fmt: str) -> Any:
        if fmt == "json":
            return {"format": "json", "content": s.audit.export_json()}
        if fmt == "csv":
            return {"format": "csv", "content": s.audit.export_csv()}
        return _error(404, "unknown_format", "format must be json or csv")

    @router.get("/grants")
    def grants() -> Any:
        return GrantList(grants=[GrantView.model_validate(asdict(g)) for g in s.grants.active()])

    @router.post("/grants")
    def add_grant(body: GrantCreate) -> Any:
        if body.scope_type not in SCOPE_TYPES:
            return _error(422, "invalid_scope", "unknown scope type")
        grant = s.grants.add(body.scope_type, body.scope_value, body.expires_at)
        s.audit.append("permission.granted", asdict(grant), actor="user")
        return GrantView.model_validate(asdict(grant))

    @router.post("/grants/{grant_id}/revoke")
    def revoke(grant_id: str) -> Any:
        if not s.grants.revoke(grant_id):
            return _error(404, "unknown_grant", "no such active grant")
        s.audit.append("permission.revoked", {"grant_id": grant_id}, actor="user")
        return {"revoked": grant_id}

    return router
