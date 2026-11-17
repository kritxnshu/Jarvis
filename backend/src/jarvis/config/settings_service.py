"""Validates settings against the registry and persists them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from jarvis.config.settings_registry import SETTINGS, SettingSpec
from jarvis.storage.settings_repo import SettingsRepository


class UnknownSettingError(KeyError):
    pass


class InvalidSettingValueError(ValueError):
    pass


@dataclass(frozen=True)
class SettingView:
    key: str
    value: Any
    default: Any
    description: str
    is_default: bool


class SettingsService:
    def __init__(self, repo: SettingsRepository, registry: dict[str, SettingSpec] | None = None):
        self._repo = repo
        self._registry = SETTINGS if registry is None else registry

    def list(self) -> list[SettingView]:
        stored = self._repo.all()
        views: list[SettingView] = []
        for key, spec in sorted(self._registry.items()):
            has_value = key in stored
            views.append(
                SettingView(
                    key=key,
                    value=stored[key] if has_value else spec.default,
                    default=spec.default,
                    description=spec.description,
                    is_default=not has_value,
                )
            )
        return views

    def set(self, key: str, value: Any) -> SettingView:
        spec = self._registry.get(key)
        if spec is None:
            raise UnknownSettingError(key)
        try:
            validated = spec.adapter.validate_python(value)
        except ValidationError:
            # Do not echo the submitted value: it may contain something sensitive.
            raise InvalidSettingValueError(f"invalid value for setting {key!r}") from None
        self._repo.put(key, validated)
        return SettingView(key, validated, spec.default, spec.description, is_default=False)
