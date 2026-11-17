"""Request/response models. These are the source of truth for generated TS contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    version: str
    schema_version: int


class Setting(BaseModel):
    key: str
    value: Any
    default: Any
    description: str
    is_default: bool


class SettingsResponse(BaseModel):
    settings: list[Setting]


class SettingUpdate(BaseModel):
    value: Any


# ---- M2: trust kernel views ------------------------------------------------------------


class TaskView(BaseModel):
    id: str
    objective: str
    state: str
    state_reason: str | None
    created_at: str
    updated_at: str


class TaskList(BaseModel):
    tasks: list[TaskView]


class IntentView(BaseModel):
    intent_id: str
    attempt: int
    idempotency_key: str
    started_at: str
    outcome: str | None
    detail: dict[str, Any] | None
    finished_at: str | None


class ReceiptAction(BaseModel):
    action_id: str
    tool: str
    tool_version: int
    parameters: dict[str, Any]
    digest: str
    state: str
    status_label: str
    attempts: int
    approval_id: str | None
    intents: list[IntentView]
    verification: dict[str, Any] | None
    error: str | None


class PlanStep(BaseModel):
    step: int
    tool: str
    parameters: dict[str, Any]


class OutstandingAction(BaseModel):
    action_id: str
    state: str


class Receipt(BaseModel):
    task_id: str
    objective: str
    plan: list[PlanStep]
    actions: list[ReceiptAction]
    tools_used: list[str]
    files: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    tests: list[dict[str, Any]]
    errors_and_recovery: list[dict[str, Any]]
    final_status: str
    final_status_reason: str | None
    verification_evidence: list[dict[str, Any]]
    outstanding_actions: list[OutstandingAction]
    created_at: str
    updated_at: str


class TaskDetail(BaseModel):
    task: TaskView
    receipt: Receipt


class ExecutionView(BaseModel):
    task_id: str
    action_id: str
    task_state: str
    action_state: str
    approval_id: str | None
    receipt: Receipt


class ApprovalRequestText(BaseModel):
    intent: str
    why: str
    service: str
    data_affected: str
    consequences: str
    parameters: dict[str, Any]


class ApprovalView(BaseModel):
    id: str
    action_id: str
    digest: str
    category: str | None
    highest_risk: bool
    request: ApprovalRequestText
    status: str
    created_at: str
    expires_at: str
    decided_at: str | None
    native_confirmed: bool
    used_at: str | None


class ApprovalList(BaseModel):
    approvals: list[ApprovalView]


class AuditEntryView(BaseModel):
    seq: int
    ts: str
    type: str
    actor: str
    task_id: str | None
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class AuditEntries(BaseModel):
    entries: list[AuditEntryView]


class ChainVerificationView(BaseModel):
    ok: bool
    entries: int
    first_bad_seq: int | None
    reason: str | None


class GrantView(BaseModel):
    id: str
    scope_type: str
    scope_value: str
    expires_at: str | None


class GrantList(BaseModel):
    grants: list[GrantView]


# ---- M3: providers and conversation ------------------------------------------------------


class ProviderView(BaseModel):
    id: str
    kind: str
    display_name: str
    base_url: str
    key_optional: bool
    enabled: bool
    has_credential: bool
    credential_hint: str | None
    configured: bool
    retention_policy_url: str | None


class RouteStepView(BaseModel):
    provider_id: str
    model: str


class ProvidersResponse(BaseModel):
    providers: list[ProviderView]
    routes: dict[str, list[RouteStepView]]


class ProviderUpdate(BaseModel):
    base_url: str | None = None
    enabled: bool | None = None
    key_optional: bool | None = None


class CredentialUpdate(BaseModel):
    secret: str


class RouteUpdate(BaseModel):
    chain: list[RouteStepView]


class HealthCheckView(BaseModel):
    ok: bool
    detail: str
    models: list[str]
    error_kind: str | None


class ConversationView(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationList(BaseModel):
    conversations: list[ConversationView]


class ConversationCreate(BaseModel):
    title: str = "New conversation"


class ChatMessageView(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    status: str
    provider_id: str | None
    model: str | None
    error: str | None
    created_at: str


class MessageList(BaseModel):
    messages: list[ChatMessageView]


class SendMessage(BaseModel):
    text: str


class SendResult(BaseModel):
    user_message_id: str
    message_id: str


class StopResult(BaseModel):
    stopped: bool
