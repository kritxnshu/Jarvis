"""Configured providers, their credentials (Keychain) and per-task routes."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from jarvis.clock import Clock, SystemClock, to_iso
from jarvis.providers.adapters import ADAPTERS, OpenAICompatAdapter
from jarvis.providers.http import HttpAdapter
from jarvis.storage.db import Database
from jarvis.trust.audit import AuditLog
from jarvis.trust.redaction import Redactor
from jarvis.trust.secrets import SecretStore, mask

TASKS = ("chat", "planning", "memory_extraction", "vision", "embeddings")

# ADR-0012: free-first defaults. Ollama is local and free; the others stay "Not configured"
# until the user saves a key.
DEFAULT_PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "id": "ollama",
        "kind": "ollama",
        "display_name": "Ollama (local, free)",
        "base_url": "http://127.0.0.1:11434",
        "key_optional": 1,
        "retention_policy_url": None,
    },
    {
        "id": "gemini",
        "kind": "gemini",
        "display_name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "key_optional": 0,
        "retention_policy_url": "https://ai.google.dev/gemini-api/terms",
    },
    {
        "id": "anthropic",
        "kind": "anthropic",
        "display_name": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "key_optional": 0,
        "retention_policy_url": "https://www.anthropic.com/legal/privacy",
    },
    {
        "id": "openai",
        "kind": "openai",
        "display_name": "OpenAI-compatible",
        "base_url": "https://api.openai.com/v1",
        "key_optional": 0,
        "retention_policy_url": "https://openai.com/policies/privacy-policy",
    },
)
DEFAULT_ROUTES: dict[str, list[dict[str, str]]] = {
    "chat": [{"provider_id": "ollama", "model": "llama3.2"}],
    "planning": [{"provider_id": "ollama", "model": "llama3.2"}],
    "memory_extraction": [{"provider_id": "ollama", "model": "llama3.2"}],
    "embeddings": [{"provider_id": "ollama", "model": "nomic-embed-text"}],
    "vision": [],
}


class UnknownProviderError(KeyError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    kind: str
    display_name: str
    base_url: str
    key_optional: bool
    enabled: bool
    has_credential: bool
    credential_hint: str | None
    retention_policy_url: str | None

    @property
    def configured(self) -> bool:
        return self.enabled and (self.key_optional or self.has_credential)


@dataclass(frozen=True)
class RouteStep:
    provider_id: str
    model: str


TransportFactory = Callable[[str], httpx.AsyncBaseTransport | None]


def _no_transport(_provider_id: str) -> httpx.AsyncBaseTransport | None:
    return None


def _secret_name(provider_id: str) -> str:
    return f"provider:{provider_id}:api_key"


class ProviderRegistry:
    def __init__(
        self,
        db: Database,
        secrets: SecretStore,
        redactor: Redactor,
        audit: AuditLog,
        clock: Clock | None = None,
        transport: TransportFactory | None = None,
    ) -> None:
        self._db = db
        self._secrets = secrets
        self._redactor = redactor
        self._audit = audit
        self._clock = clock or SystemClock()
        self._transport: TransportFactory = transport or _no_transport

    def seed_defaults(self) -> None:
        now = to_iso(self._clock.now())
        with self._db.transaction() as conn:
            for p in DEFAULT_PROVIDERS:
                conn.execute(
                    "INSERT OR IGNORE INTO providers (id, kind, display_name, base_url,"
                    " key_optional, retention_policy_url, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (
                        p["id"],
                        p["kind"],
                        p["display_name"],
                        p["base_url"],
                        p["key_optional"],
                        p["retention_policy_url"],
                        now,
                        now,
                    ),
                )
            for task, chain in DEFAULT_ROUTES.items():
                conn.execute(
                    "INSERT OR IGNORE INTO model_routes VALUES (?,?,?)",
                    (task, json.dumps(chain), now),
                )
        # Keys already in the Keychain are redacted everywhere from the first log line on.
        for p in self.list():
            if p.has_credential:
                value = self._secrets.get(_secret_name(p.id))
                if value and len(value) >= 8:
                    self._redactor.register(value)

    # -- providers --------------------------------------------------------------------------
    def list(self) -> list[ProviderConfig]:
        rows = self._db.query("SELECT * FROM providers ORDER BY rowid")
        return [self._config(r) for r in rows]

    def get(self, provider_id: str) -> ProviderConfig:
        rows = self._db.query("SELECT * FROM providers WHERE id = ?", (provider_id,))
        if not rows:
            raise UnknownProviderError(provider_id)
        return self._config(rows[0])

    @staticmethod
    def _config(r: Any) -> ProviderConfig:
        return ProviderConfig(
            r["id"],
            r["kind"],
            r["display_name"],
            r["base_url"],
            bool(r["key_optional"]),
            bool(r["enabled"]),
            bool(r["has_credential"]),
            r["credential_hint"],
            r["retention_policy_url"],
        )

    def update(
        self,
        provider_id: str,
        *,
        base_url: str | None = None,
        enabled: bool | None = None,
        key_optional: bool | None = None,
    ) -> ProviderConfig:
        current = self.get(provider_id)
        if key_optional is not None and current.kind != "openai":
            raise ValueError("only OpenAI-compatible providers can run without a key")
        values = {
            "base_url": base_url if base_url is not None else current.base_url,
            "enabled": int(enabled if enabled is not None else current.enabled),
            "key_optional": int(key_optional if key_optional is not None else current.key_optional),
        }
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE providers SET base_url = ?, enabled = ?, key_optional = ?, updated_at = ?"
                " WHERE id = ?",
                (
                    values["base_url"],
                    values["enabled"],
                    values["key_optional"],
                    to_iso(self._clock.now()),
                    provider_id,
                ),
            )
            self._audit.append(
                "provider.changed", {"provider_id": provider_id, **values}, actor="user", conn=conn
            )
        return self.get(provider_id)

    def save_credential(self, provider_id: str, value: str) -> ProviderConfig:
        self.get(provider_id)
        value = value.strip()
        if len(value) < 8:
            raise ValueError("that does not look like an API key")
        self._redactor.register(value)  # before anything else can log it
        self._secrets.set(_secret_name(provider_id), value)  # Keychain only
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE providers SET has_credential = 1, credential_hint = ?, updated_at = ?"
                " WHERE id = ?",
                (mask(value), to_iso(self._clock.now()), provider_id),
            )
            self._audit.append(
                "provider.credential_saved", {"provider_id": provider_id}, actor="user", conn=conn
            )
        return self.get(provider_id)

    def delete_credential(self, provider_id: str) -> ProviderConfig:
        self.get(provider_id)
        self._secrets.delete(_secret_name(provider_id))
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE providers SET has_credential = 0, credential_hint = NULL, updated_at = ?"
                " WHERE id = ?",
                (to_iso(self._clock.now()), provider_id),
            )
            self._audit.append(
                "provider.credential_deleted", {"provider_id": provider_id}, actor="user", conn=conn
            )
        return self.get(provider_id)

    def adapter(self, provider_id: str) -> HttpAdapter:
        cfg = self.get(provider_id)
        key = self._secrets.get(_secret_name(provider_id)) if cfg.has_credential else None
        instance = ADAPTERS[cfg.kind](cfg.id, cfg.base_url, key, transport=self._transport(cfg.id))
        if isinstance(instance, OpenAICompatAdapter):
            instance.key_optional = cfg.key_optional
        return instance

    # -- routes ------------------------------------------------------------------------------
    def route(self, task: str) -> list[RouteStep]:
        rows = self._db.query("SELECT chain_json FROM model_routes WHERE task = ?", (task,))
        chain: list[dict[str, str]] = json.loads(rows[0][0]) if rows else []
        return [RouteStep(step["provider_id"], step["model"]) for step in chain]

    def routes(self) -> dict[str, list[RouteStep]]:
        return {task: self.route(task) for task in TASKS}

    def set_route(self, task: str, chain: list[RouteStep]) -> None:
        if task not in TASKS:
            raise ValueError(f"unknown task {task!r}")
        for step in chain:
            self.get(step.provider_id)
            if not step.model.strip():
                raise ValueError("every route step needs a model name")
        data = [{"provider_id": s.provider_id, "model": s.model} for s in chain]
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO model_routes VALUES (?,?,?) ON CONFLICT(task) DO UPDATE SET"
                " chain_json = excluded.chain_json, updated_at = excluded.updated_at",
                (task, json.dumps(data), to_iso(self._clock.now())),
            )
            self._audit.append(
                "provider.changed", {"route": task, "chain": data}, actor="user", conn=conn
            )
