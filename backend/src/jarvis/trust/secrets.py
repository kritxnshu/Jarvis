"""Credential storage (ADR-0008). Secrets live only in the OS keychain; SQLite stores nothing
but the fact that a credential exists. Every stored secret is registered with the redactor."""

from __future__ import annotations

import threading
from typing import Protocol

SERVICE = "ai.jarvis.desktop"


class SecretStoreUnavailableError(Exception):
    """The OS keychain cannot be used (e.g. no keyring backend on this machine)."""


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...


class KeychainSecretStore:
    """macOS Keychain via the `keyring` package (other OS keyrings where available)."""

    def __init__(self, service: str = SERVICE) -> None:
        self._service = service

    def _keyring(self):  # type: ignore[no-untyped-def]
        try:
            import keyring
            from keyring.backends import fail
        except ImportError as exc:  # pragma: no cover - dependency always installed
            raise SecretStoreUnavailableError("keyring is not installed") from exc
        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring):
            raise SecretStoreUnavailableError("no OS keychain is available on this machine")
        return keyring

    def get(self, name: str) -> str | None:
        try:
            value: str | None = self._keyring().get_password(self._service, name)
        except SecretStoreUnavailableError:
            return None
        return value

    def set(self, name: str, value: str) -> None:
        try:
            self._keyring().set_password(self._service, name, value)
        except SecretStoreUnavailableError:
            raise
        except Exception as exc:
            raise SecretStoreUnavailableError(
                f"keychain write failed: {type(exc).__name__}"
            ) from None

    def delete(self, name: str) -> None:
        try:
            self._keyring().delete_password(self._service, name)
        except SecretStoreUnavailableError:
            raise
        except Exception:  # noqa: S110 - deleting a missing item is not an error
            pass


class MemorySecretStore:
    """In-process store for tests. Never used by the production entry point."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        with self._lock:
            return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        with self._lock:
            self._values[name] = value

    def delete(self, name: str) -> None:
        with self._lock:
            self._values.pop(name, None)


def mask(value: str) -> str:
    """What the UI may see of a stored key."""
    return "••••" + value[-4:] if len(value) >= 12 else "••••"
