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
