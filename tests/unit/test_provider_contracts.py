"""BRIEF §4.3: every adapter passes the same contract tests against fixtures —
streaming, tool calls, 429, 5xx, timeout and malformed responses."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from jarvis.providers.adapters import (
    AnthropicAdapter,
    GeminiAdapter,
    OllamaAdapter,
    OpenAICompatAdapter,
)
from jarvis.providers.http import HttpAdapter
from jarvis.providers.types import (
    ChatRequest,
    Done,
    Message,
    ProviderError,
    ProviderErrorKind,
    Role,
    StreamEvent,
    TextDelta,
    ToolCallEvent,
    ToolSpec,
    UsageEvent,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "providers"
KEY = "test-key-not-a-real-secret"


@dataclass(frozen=True)
class Case:
    name: str
    cls: type[HttpAdapter]
    ext: str
    content_type: str
    key: str | None
    auth_header: str | None


CASES = [
    Case("anthropic", AnthropicAdapter, "sse", "text/event-stream", KEY, "x-api-key"),
    Case("openai", OpenAICompatAdapter, "sse", "text/event-stream", KEY, "authorization"),
    Case("gemini", GeminiAdapter, "sse", "text/event-stream", KEY, "x-goog-api-key"),
    Case("ollama", OllamaAdapter, "ndjson", "application/x-ndjson", None, None),
]
IDS = [c.name for c in CASES]

REQUEST = ChatRequest(
    model="m",
    messages=(Message(Role.SYSTEM, "Be brief."), Message(Role.USER, "Greet Priya.")),
    tools=(
        ToolSpec(
            "get_weather",
            "Weather for a city",
            {"type": "object", "properties": {"city": {"type": "string"}}},
        ),
    ),
)

Handler = Callable[[httpx.Request], httpx.Response]


def adapter(case: Case, handler: Handler) -> HttpAdapter:
    return case.cls("p1", "https://provider.test", case.key, transport=httpx.MockTransport(handler))


def fixture_handler(case: Case, kind: str, seen: list[httpx.Request] | None = None) -> Handler:
    body = (FIXTURES / f"{case.name}_{kind}.{case.ext}").read_bytes()

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, content=body, headers={"content-type": case.content_type})

    return handle


def collect(a: HttpAdapter, req: ChatRequest = REQUEST) -> list[StreamEvent]:
    async def go() -> list[StreamEvent]:
        return [e async for e in a.stream(req)]  # type: ignore[attr-defined]

    return asyncio.run(go())


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_streams_text_deltas_usage_and_done(case: Case) -> None:
    seen: list[httpx.Request] = []
    events = collect(adapter(case, fixture_handler(case, "text", seen)))
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "Hello, Priya."
    assert len([e for e in events if isinstance(e, TextDelta)]) >= 2  # really streamed
    usage = [e.usage for e in events if isinstance(e, UsageEvent)]
    assert usage
    assert usage[-1].output_tokens == 5
    assert isinstance(events[-1], Done)
    assert events[-1].stop_reason == "end_turn"
    [request] = seen
    assert KEY not in str(request.url)  # keys travel in headers, never in URLs
    if case.auth_header:
        assert KEY in request.headers[case.auth_header]
    body = json.loads(request.content)
    assert "Greet Priya." in json.dumps(body)
    assert "Be brief." in json.dumps(body)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_assembles_tool_calls(case: Case) -> None:
    events = collect(adapter(case, fixture_handler(case, "tool")))
    calls = [e.call for e in events if isinstance(e, ToolCallEvent)]
    assert len(calls) == 1
    assert calls[0].name == "get_weather"
    assert calls[0].arguments == {"city": "Paris"}
    assert calls[0].id
    done = events[-1]
    assert isinstance(done, Done)
    assert done.stop_reason == "tool_use"


@pytest.mark.parametrize("case", CASES, ids=IDS)
@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [
        (429, ProviderErrorKind.RATE_LIMITED, True),
        (500, ProviderErrorKind.SERVER, True),
        (503, ProviderErrorKind.SERVER, True),
        (401, ProviderErrorKind.AUTH, False),
        (400, ProviderErrorKind.BAD_REQUEST, False),
    ],
)
def test_http_errors_are_normalized(
    case: Case, status: int, kind: ProviderErrorKind, retryable: bool
) -> None:
    def handle(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, json={"error": {"message": "nope"}}, headers={"retry-after": "7"}
        )

    with pytest.raises(ProviderError) as info:
        collect(adapter(case, handle))
    assert info.value.kind is kind
    assert info.value.retryable is retryable
    assert info.value.status == status
    if status == 429:
        assert info.value.retry_after == 7.0


@pytest.mark.parametrize("case", CASES, ids=IDS)
@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (httpx.ReadTimeout("slow"), ProviderErrorKind.TIMEOUT),
        (httpx.ConnectError("refused"), ProviderErrorKind.UNAVAILABLE),
    ],
    ids=["timeout", "connect"],
)
def test_transport_failures_are_normalized(
    case: Case, exc: Exception, kind: ProviderErrorKind
) -> None:
    def handle(_r: httpx.Request) -> httpx.Response:
        raise exc

    with pytest.raises(ProviderError) as info:
        collect(adapter(case, handle))
    assert info.value.kind is kind
    assert info.value.retryable


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_malformed_payload_is_reported_not_guessed(case: Case) -> None:
    garbage = b"data: {not json\n\n" if case.ext == "sse" else b"{not json\n"

    def handle(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=garbage, headers={"content-type": case.content_type})

    with pytest.raises(ProviderError) as info:
        collect(adapter(case, handle))
    assert info.value.kind is ProviderErrorKind.MALFORMED


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_truncated_stream_is_malformed_not_success(case: Case) -> None:
    full = (FIXTURES / f"{case.name}_text.{case.ext}").read_text().splitlines(keepends=True)
    cut = "".join(full[: max(1, len(full) // 2)]).encode()
    if case.name == "gemini":  # a single chunk without finishReason
        cut = (FIXTURES / "gemini_text.sse").read_text().split("\n\n")[0].encode() + b"\n\n"

    def handle(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=cut, headers={"content-type": case.content_type})

    with pytest.raises(ProviderError) as info:
        collect(adapter(case, handle))
    assert info.value.kind is ProviderErrorKind.MALFORMED


@pytest.mark.parametrize("case", [c for c in CASES if c.key], ids=[c.name for c in CASES if c.key])
def test_missing_key_is_not_configured(case: Case) -> None:
    a = case.cls(
        "p1",
        "https://provider.test",
        None,
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )
    with pytest.raises(ProviderError) as info:
        collect(a)
    assert info.value.kind is ProviderErrorKind.NOT_CONFIGURED


def test_ollama_health_explains_missing_model() -> None:
    a = OllamaAdapter(
        "o",
        "http://127.0.0.1:11434",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"models": []})),
    )
    result = asyncio.run(a.check())
    assert not result.ok
    assert "ollama pull" in result.detail


def test_openai_compatible_local_server_may_run_without_a_key() -> None:
    seen: list[httpx.Request] = []
    a = OpenAICompatAdapter(
        "lm",
        "http://127.0.0.1:1234/v1",
        None,
        transport=httpx.MockTransport(fixture_handler(CASES[1], "text", seen)),
    )
    a.key_optional = True
    events = collect(a)
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello, Priya."
    assert "authorization" not in seen[0].headers
