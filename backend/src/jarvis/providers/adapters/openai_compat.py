"""OpenAI-compatible Chat Completions adapter (OpenAI and OpenAI-style servers)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from jarvis.providers.http import HttpAdapter, arr, obj, parse_json, sse
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

_STOP = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}


def _message(m: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": m.role.value, "content": m.content}
    if m.role is Role.TOOL:
        out["tool_call_id"] = m.tool_call_id
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in m.tool_calls
        ]
    return out


def build_body(req: ChatRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": req.model,
        "messages": [_message(m) for m in req.messages],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": req.max_tokens,
    }
    if req.tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in req.tools
        ]
    if req.temperature is not None:
        body["temperature"] = req.temperature
    return body


class OpenAICompatAdapter(HttpAdapter):
    kind = "openai"
    #: Local OpenAI-style servers (e.g. LM Studio) need no key; set per provider config.
    key_optional = False

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.key_optional and not self._key:
            return headers
        headers["authorization"] = f"Bearer {self._require_key()}"
        return headers

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        lines = self.lines(
            "POST",
            f"{self._base}/chat/completions",
            headers=self._headers(),
            body=build_body(request),
        )
        calls: dict[int, dict[str, str]] = {}
        stop: str | None = None
        saw_done = False
        async for _event, data in sse(lines):
            if data == "[DONE]":
                saw_done = True
                break
            chunk = parse_json(self._id, data)
            if "error" in chunk:
                raise ProviderError(ProviderErrorKind.SERVER, self._id, str(chunk["error"]))
            for choice in arr(chunk.get("choices")):
                delta = obj(choice.get("delta"))
                if delta.get("content"):
                    yield TextDelta(delta["content"])
                for tc in arr(delta.get("tool_calls")):
                    slot = calls.setdefault(
                        int(tc.get("index", 0)), {"id": "", "name": "", "args": ""}
                    )
                    fn = obj(tc.get("function"))
                    slot["id"] = tc.get("id") or slot["id"]
                    slot["name"] = fn.get("name") or slot["name"]
                    slot["args"] += fn.get("arguments") or ""
                if choice.get("finish_reason"):
                    stop = choice["finish_reason"]
            if chunk.get("usage"):
                u = chunk["usage"]
                yield UsageEvent(
                    Usage(int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)))
                )
        if not saw_done or stop is None:
            raise ProviderError(
                ProviderErrorKind.MALFORMED, self._id, "stream ended before completion"
            )
        for _index, c in sorted(calls.items()):
            args = obj(parse_json(self._id, c["args"])) if c["args"] else {}
            yield ToolCallEvent(ToolCall(c["id"], c["name"], args))
        yield Done(_STOP.get(stop, "other"))

    async def check(self) -> HealthResult:
        body = await self.get_json(f"{self._base}/models", self._headers())
        models = tuple(m["id"] for m in body.get("data", []))
        return HealthResult(True, f"reachable; {len(models)} models listed", models)
