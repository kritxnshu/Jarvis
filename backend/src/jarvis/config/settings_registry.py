"""The settings JARVIS understands. A setting is listed here only once something honors it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import StrictBool, TypeAdapter


@dataclass(frozen=True)
class SettingSpec:
    key: str
    description: str
    adapter: TypeAdapter[Any]
    default: Any


ReducedMotion = Literal["system", "on", "off"]

SETTINGS: dict[str, SettingSpec] = {
    spec.key: spec
    for spec in (
        SettingSpec(
            key="appearance.reduced_motion",
            description="Reduce interface motion: follow the system setting, or force on/off.",
            adapter=TypeAdapter(ReducedMotion),
            default="system",
        ),
        SettingSpec(
            key="appearance.show_status_bar",
            description="Show the backend connection status bar at the bottom of the window.",
            adapter=TypeAdapter(StrictBool),
            default=True,
        ),
    )
}
