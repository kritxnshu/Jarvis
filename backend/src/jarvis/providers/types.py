"""The normalized model interface (BRIEF §4.3). Application code depends only on these types;
vendor wire formats live exclusively in the adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None  # for Role.TOOL results
    name: str | None = None  # tool name for Role.TOOL results (Gemini needs it)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    max_tokens: int = 1024
    temperature: float | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


# ---- stream events ------------------------------------------------------------------------


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallEvent:
    """Emitted once a tool call's arguments are complete (adapters assemble partial JSON)."""

    call: ToolCall


@dataclass(frozen=True)
class UsageEvent:
    usage: Usage


@dataclass(frozen=True)
class Done:
    stop_reason: str  # end_turn | tool_use | max_tokens | stop | other


StreamEvent = TextDelta | ToolCallEvent | UsageEvent | Done


# ---- errors -------------------------------------------------------------------------------


class ProviderErrorKind(StrEnum):
    RATE_LIMITED = "rate_limited"
    SERVER = "server"
    TIMEOUT = "timeout"
    MALFORMED = "malformed"
    AUTH = "auth"
    BAD_REQUEST = "bad_request"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    NOT_SUPPORTED = "not_supported"


RETRYABLE = frozenset(
    {
        ProviderErrorKind.RATE_LIMITED,
        ProviderErrorKind.SERVER,
        ProviderErrorKind.TIMEOUT,
        ProviderErrorKind.UNAVAILABLE,
    }
)


class ProviderError(Exception):
    def __init__(
        self,
        kind: ProviderErrorKind,
        provider: str,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.provider = provider
        self.status = status
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    detail: str
    models: tuple[str, ...] = field(default_factory=tuple)


class ModelProvider(Protocol):
    """One configured provider instance. Implementations live in jarvis.providers.adapters."""

    @property
    def provider_id(self) -> str: ...

    def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]: ...

    async def check(self) -> HealthResult: ...
