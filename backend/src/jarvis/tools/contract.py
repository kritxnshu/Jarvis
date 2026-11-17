"""The tool contract (BRIEF §5.4). Tools run only through the executor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel


class Risk(StrEnum):
    READ_ONLY = "read_only"
    LOW = "low"
    CONSEQUENTIAL = "consequential"  # needs approval
    HIGHEST = "highest"  # needs approval + native macOS confirmation


class ApprovalCategory(StrEnum):
    SEND_MESSAGE = "send_message"
    PUBLISH = "publish"
    PURCHASE = "purchase"
    DELETE_IMPORTANT = "delete_important"
    PERMANENT_DELETE = "permanent_delete"
    DESTRUCTIVE_COMMAND = "destructive_command"
    ACCOUNT_SETTINGS = "account_settings"
    SHARE_PRIVATE = "share_private"
    PRODUCTION_DEPLOY = "production_deploy"
    EXTERNAL_ACTION = "external_action"


# BRIEF §4.11: these need a native confirmation outside the webview.
HIGHEST_RISK_CATEGORIES = frozenset(
    {
        ApprovalCategory.PURCHASE,
        ApprovalCategory.SEND_MESSAGE,
        ApprovalCategory.PUBLISH,
        ApprovalCategory.PERMANENT_DELETE,
        ApprovalCategory.PRODUCTION_DEPLOY,
    }
)


class Recovery(StrEnum):
    IDEMPOTENT = "idempotent"
    RECONCILABLE = "reconcilable"
    MANUAL = "manual"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class Verification:
    status: VerificationStatus
    evidence: dict[str, Any] = field(default_factory=dict[str, Any])


class ReconcileOutcome(StrEnum):
    HAPPENED = "happened"
    NOT_HAPPENED = "not_happened"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Reconciliation:
    outcome: ReconcileOutcome
    evidence: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True)
class PermissionNeed:
    scope_type: str  # directory | domain | command_class | tool
    value: str


@dataclass(frozen=True)
class ApprovalText:
    """What the user sees in the approval request (BRIEF §4.11)."""

    intent: str
    why: str
    service: str
    data_affected: str
    consequences: str


@dataclass(frozen=True)
class ExecContext:
    action_id: str
    idempotency_key: str
    attempt: int


class Tool[In: BaseModel, Out: BaseModel](ABC):
    """Subclasses declare their contract as class attributes and implement execute/verify."""

    name: ClassVar[str]
    version: ClassVar[int] = 1
    input_model: type[In]
    output_model: type[Out]
    risk: ClassVar[Risk]
    category: ClassVar[ApprovalCategory | None] = None
    side_effects: ClassVar[bool] = True
    idempotent: ClassVar[bool] = False
    recovery: ClassVar[Recovery | None] = None
    timeout_s: ClassVar[float] = 30.0

    def permissions(self, inp: In) -> list[PermissionNeed]:
        """Grants this call needs. Default: none beyond the risk-based policy."""
        del inp
        return []

    def describe(self, inp: In) -> ApprovalText:
        return ApprovalText(
            intent=f"Run {self.name}",
            why="Requested in the current task.",
            service=self.name,
            data_affected="See parameters.",
            consequences="Unknown; review the parameters.",
        )

    @abstractmethod
    async def execute(self, inp: In, ctx: ExecContext) -> Out: ...

    @abstractmethod
    async def verify(self, inp: In, out: Out, ctx: ExecContext) -> Verification: ...

    async def reconcile(self, inp: In, ctx: ExecContext) -> Reconciliation:
        """Determine whether an uncertain action happened. Reconcilable tools override this."""
        del inp, ctx
        return Reconciliation(ReconcileOutcome.INCONCLUSIVE, {"reason": "tool cannot reconcile"})


AnyTool = Tool[Any, Any]
