"""Ollama adapter (local models; NDJSON streaming from /api/chat). Needs no key."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from jarvis.ids import new_id
from jarvis.providers.http import HttpAdapter, arr, obj, parse_json
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

_STOP = {"stop": "end_turn", "length": "max_tokens"}


def _message(m: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": m.role.value, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            {"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls
        ]
    if m.role is Role.TOOL and m.name:
        out["tool_name"] = m.name
    return out


def build_body(req: ChatRequest) -> dict[str, Any]:
    options: dict[str, Any] = {"num_predict": req.max_tokens}
    if req.temperature is not None:
        options["temperature"] = req.temperature
    body: dict[str, Any] = {
        "model": req.model,
        "messages": [_message(m) for m in req.messages],
        "stream": True,
        "options": options,
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
    return body


class OllamaAdapter(HttpAdapter):
    kind = "ollama"

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        lines = self.lines(
            "POST",
            f"{self._base}/api/chat",
            headers={"content-type": "application/json"},
            body=build_body(request),
        )
        saw_call = False
        async for line in lines:
            if not line.strip():
                continue
            chunk = parse_json(self._id, line)
            if "error" in chunk:
                raise ProviderError(ProviderErrorKind.SERVER, self._id, str(chunk["error"]))
            message = obj(chunk.get("message"))
            if message.get("content"):
                yield TextDelta(message["content"])
            for tc in arr(message.get("tool_calls")):
                fn = obj(tc.get("function"))
                saw_call = True
                yield ToolCallEvent(
                    ToolCall(new_id(), fn.get("name", ""), obj(fn.get("arguments")))
                )
            if chunk.get("done"):
                yield UsageEvent(
                    Usage(int(chunk.get("prompt_eval_count", 0)), int(chunk.get("eval_count", 0)))
                )
                reason = chunk.get("done_reason", "stop")
                yield Done("tool_use" if saw_call else _STOP.get(reason, "other"))
                return
        raise ProviderError(ProviderErrorKind.MALFORMED, self._id, "stream ended before done:true")

    async def check(self) -> HealthResult:
        body = await self.get_json(f"{self._base}/api/tags", {})
        models = tuple(m["name"] for m in body.get("models", []))
        if not models:
            return HealthResult(
                False,
                "Ollama is running but no model is installed (run: ollama pull llama3.2)",
                models,
            )
        return HealthResult(True, f"reachable; {len(models)} local models", models)
