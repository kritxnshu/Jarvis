"""Composition root: builds every backend service from its dependencies (DI in one place)."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.clock import Clock, SystemClock
from jarvis.config.settings_service import SettingsService
from jarvis.core.chat import ChatService
from jarvis.core.routing import ModelRouter
from jarvis.events import EventBus
from jarvis.execution.executor import Executor
from jarvis.execution.store import TaskStore
from jarvis.providers.registry import ProviderRegistry, TransportFactory
from jarvis.storage.db import Database
from jarvis.storage.settings_repo import SettingsRepository
from jarvis.tools.registry import ToolRegistry
from jarvis.trust.approvals import ApprovalService
from jarvis.trust.audit import AuditLog
from jarvis.trust.policy import GrantStore, PolicyEngine
from jarvis.trust.redaction import Redactor
from jarvis.trust.secrets import KeychainSecretStore, SecretStore


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
    providers: ProviderRegistry
    chat: ChatService


def build_services(
    db: Database,
    redactor: Redactor,
    secret: str,
    registry: ToolRegistry,
    clock: Clock | None = None,
    *,
    secrets: SecretStore | None = None,
    transport: TransportFactory | None = None,
) -> Services:
    clock = clock or SystemClock()
    audit = AuditLog(db, redactor, clock)
    grants = GrantStore(db, clock)
    approvals = ApprovalService(db, audit, redactor, secret, clock)
    store = TaskStore(db, audit, redactor, clock)
    executor = Executor(store, registry, PolicyEngine(grants), approvals, audit)
    providers = ProviderRegistry(
        db, secrets or KeychainSecretStore(), redactor, audit, clock, transport
    )
    providers.seed_defaults()
    bus = EventBus()
    chat = ChatService(db, ModelRouter(providers, audit), bus, audit, redactor, clock)
    return Services(
        db=db,
        redactor=redactor,
        audit=audit,
        settings=SettingsService(SettingsRepository(db)),
        grants=grants,
        approvals=approvals,
        store=store,
        executor=executor,
        bus=bus,
        providers=providers,
        chat=chat,
    )
