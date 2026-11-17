"""Anthropic Messages API adapter (streaming SSE)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from jarvis.providers.http import HttpAdapter, obj, parse_json, sse
from jarvis.providers.types import (
    ChatRequest,
    Done,
    HealthResult,
    Message,
    ProviderError,
    ProviderErrorKind,
    Role,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    Usage,
    UsageEvent,
)

API_VERSION = "2023-06-01"
_STOP = {
    "end_turn": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "stop_sequence": "stop",
}
_ERRORS = {
    "rate_limit_error": ProviderErrorKind.RATE_LIMITED,
    "overloaded_error": ProviderErrorKind.SERVER,
    "api_error": ProviderErrorKind.SERVER,
    "authentication_error": ProviderErrorKind.AUTH,
    "permission_error": ProviderErrorKind.AUTH,
}


def _content(m: Message) -> list[dict[str, Any]] | str:
    if m.role is Role.TOOL:
        return [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}]
    if m.tool_calls:
        blocks: list[dict[str, Any]] = [{"type": "text", "text": m.content}] if m.content else []
        blocks += [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
            for c in m.tool_calls
        ]
        return blocks
    return m.content


def build_body(req: ChatRequest) -> dict[str, Any]:
    system = "\n\n".join(m.content for m in req.messages if m.role is Role.SYSTEM)
    messages = [
        {
            "role": "user" if m.role in (Role.USER, Role.TOOL) else "assistant",
            "content": _content(m),
        }
        for m in req.messages
        if m.role is not Role.SYSTEM
    ]
    body: dict[str, Any] = {
        "model": req.model,
        "max_tokens": req.max_tokens,
        "messages": messages,
        "stream": True,
    }
    if system:
        body["system"] = system
    if req.tools:
        body["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in req.tools
        ]
    if req.temperature is not None:
        body["temperature"] = req.temperature
    return body


class AnthropicAdapter(HttpAdapter):
    kind = "anthropic"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._require_key(),
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        lines = self.lines(
            "POST", f"{self._base}/v1/messages", headers=self._headers(), body=build_body(request)
        )
        tools: dict[int, dict[str, Any]] = {}
        input_tokens = 0
        finished = False
        async for event, data in sse(lines):
            payload = parse_json(self._id, data)
            kind = payload.get("type", event)
            if kind == "message_start":
                input_tokens = int(payload["message"].get("usage", {}).get("input_tokens", 0))
            elif kind == "content_block_start":
                block = payload["content_block"]
                if block.get("type") == "tool_use":
                    tools[payload["index"]] = {"id": block["id"], "name": block["name"], "json": ""}
            elif kind == "content_block_delta":
                delta = payload["delta"]
                if delta.get("type") == "text_delta":
                    yield TextDelta(delta["text"])
                elif delta.get("type") == "input_json_delta":
                    tools[payload["index"]]["json"] += delta.get("partial_json", "")
            elif kind == "content_block_stop" and payload["index"] in tools:
                t = tools.pop(payload["index"])
                args = obj(parse_json(self._id, t["json"])) if t["json"] else {}
                yield ToolCallEvent(ToolCall(t["id"], t["name"], args))
            elif kind == "message_delta":
                out = int(payload.get("usage", {}).get("output_tokens", 0))
                yield UsageEvent(Usage(input_tokens, out))
                reason = payload.get("delta", {}).get("stop_reason") or "end_turn"
                yield Done(_STOP.get(reason, "other"))
                finished = True
            elif kind == "error":
                err = payload.get("error", {})
                raise ProviderError(
                    _ERRORS.get(err.get("type", ""), ProviderErrorKind.SERVER),
                    self._id,
                    str(err.get("message", "stream error")),
                )
        if not finished:
            raise ProviderError(
                ProviderErrorKind.MALFORMED, self._id, "stream ended before message_delta"
            )

    async def check(self) -> HealthResult:
        body = await self.get_json(f"{self._base}/v1/models", self._headers())
        models = tuple(m["id"] for m in body.get("data", []))
        return HealthResult(True, f"reachable; {len(models)} models listed", models)
