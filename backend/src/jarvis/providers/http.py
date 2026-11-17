"""Shared HTTP plumbing for adapters: one error mapping, SSE and NDJSON line parsing, timeouts."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from jarvis.providers.types import (
    ChatRequest,
    HealthResult,
    ProviderError,
    ProviderErrorKind,
    StreamEvent,
)

DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_ERROR_BODY = 2000


def _retry_after(headers: httpx.Headers) -> float | None:
    value = headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def error_for_status(
    provider: str, response_status: int, body: str, headers: httpx.Headers
) -> ProviderError:
    snippet = body[:MAX_ERROR_BODY]
    if response_status in (401, 403):
        kind = ProviderErrorKind.AUTH
    elif response_status == 429:
        kind = ProviderErrorKind.RATE_LIMITED
    elif response_status >= 500:
        kind = ProviderErrorKind.SERVER
    else:
        kind = ProviderErrorKind.BAD_REQUEST
    return ProviderError(
        kind,
        provider,
        f"HTTP {response_status}: {snippet}",
        status=response_status,
        retry_after=_retry_after(headers),
    )


def parse_json(provider: str, text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ProviderError(
            ProviderErrorKind.MALFORMED, provider, f"invalid JSON from provider: {text[:200]!r}"
        ) from None


def obj(value: Any) -> dict[str, Any]:
    """A JSON object from parsed provider data, or {} for anything else."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def arr(value: Any) -> list[Any]:
    """A JSON array from parsed provider data, or [] for anything else."""
    return cast("list[Any]", value) if isinstance(value, list) else []


class HttpAdapter:
    """Base for adapters. ``transport`` is injectable so tests replay fixtures (MockTransport)."""

    kind = "http"

    def __init__(
        self,
        provider_id: str,
        base_url: str,
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._id = provider_id
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._transport = transport
        self._timeout = timeout

    @property
    def provider_id(self) -> str:
        return self._id

    def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        raise NotImplementedError

    async def check(self) -> HealthResult:
        raise NotImplementedError

    def _require_key(self) -> str:
        if not self._key:
            raise ProviderError(
                ProviderErrorKind.NOT_CONFIGURED, self._id, "no API key saved for this provider"
            )
        return self._key

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=self._timeout)

    async def lines(
        self, method: str, url: str, *, headers: dict[str, str], body: dict[str, Any] | None
    ) -> AsyncIterator[str]:
        """Yield response lines, mapping every transport/HTTP failure to a ProviderError."""
        try:
            async with (
                self._client() as client,
                client.stream(method, url, headers=headers, json=body) as response,
            ):
                if response.status_code >= 400:
                    text = (await response.aread()).decode(errors="replace")
                    raise error_for_status(self._id, response.status_code, text, response.headers)
                async for line in response.aiter_lines():
                    yield line
        except httpx.TimeoutException as exc:
            raise ProviderError(
                ProviderErrorKind.TIMEOUT, self._id, f"timed out: {type(exc).__name__}"
            ) from None
        except httpx.TransportError as exc:
            raise ProviderError(
                ProviderErrorKind.UNAVAILABLE, self._id, f"connection failed: {type(exc).__name__}"
            ) from None

    async def get_json(self, url: str, headers: dict[str, str]) -> Any:
        try:
            async with self._client() as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorKind.TIMEOUT, self._id, "timed out") from None
        except httpx.TransportError as exc:
            raise ProviderError(
                ProviderErrorKind.UNAVAILABLE, self._id, f"connection failed: {type(exc).__name__}"
            ) from None
        if response.status_code >= 400:
            raise error_for_status(self._id, response.status_code, response.text, response.headers)
        return parse_json(self._id, response.text)


async def sse(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str | None, str]]:
    """Server-sent events → (event, data). Multi-line data fields are joined with newlines."""
    event: str | None = None
    data: list[str] = []
    async for raw in lines:
        line = raw.rstrip("\r")
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = None, []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield event, "\n".join(data)
