"""Composition root: builds every backend service from its dependencies (DI in one place)."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.clock import Clock, SystemClock
from jarvis.config.settings_service import SettingsService
from jarvis.events import EventBus
from jarvis.execution.executor import Executor
from jarvis.execution.store import TaskStore
from jarvis.storage.db import Database
from jarvis.storage.settings_repo import SettingsRepository
from jarvis.tools.registry import ToolRegistry
from jarvis.trust.approvals import ApprovalService
from jarvis.trust.audit import AuditLog
from jarvis.trust.policy import GrantStore, PolicyEngine
from jarvis.trust.redaction import Redactor


@dataclass
class Services:
    db: Database
    redactor: Redactor
    audit: AuditLog
    settings: SettingsService
    grants: GrantStore
    approvals: ApprovalService
    store: TaskStore
    executor: Executor
    bus: EventBus


def build_services(
    db: Database,
    redactor: Redactor,
    secret: str,
    registry: ToolRegistry,
    clock: Clock | None = None,
) -> Services:
    clock = clock or SystemClock()
    audit = AuditLog(db, redactor, clock)
    grants = GrantStore(db, clock)
    approvals = ApprovalService(db, audit, redactor, secret, clock)
    store = TaskStore(db, audit, redactor, clock)
    executor = Executor(store, registry, PolicyEngine(grants), approvals, audit)
    return Services(
        db=db,
        redactor=redactor,
        audit=audit,
        settings=SettingsService(SettingsRepository(db)),
        grants=grants,
        approvals=approvals,
        store=store,
        executor=executor,
        bus=EventBus(),
    )
