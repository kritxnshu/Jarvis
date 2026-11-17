"""Google Gemini adapter (generateContent streaming over SSE)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from jarvis.ids import new_id
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

_STOP = {"STOP": "end_turn", "MAX_TOKENS": "max_tokens"}


def _parts(m: Message) -> list[dict[str, Any]]:
    if m.role is Role.TOOL:
        return [
            {"functionResponse": {"name": m.name or "tool", "response": {"content": m.content}}}
        ]
    parts: list[dict[str, Any]] = [{"text": m.content}] if m.content else []
    parts += [{"functionCall": {"name": c.name, "args": c.arguments}} for c in m.tool_calls]
    return parts


def build_body(req: ChatRequest) -> dict[str, Any]:
    system = "\n\n".join(m.content for m in req.messages if m.role is Role.SYSTEM)
    contents = [
        {"role": "model" if m.role is Role.ASSISTANT else "user", "parts": _parts(m)}
        for m in req.messages
        if m.role is not Role.SYSTEM
    ]
    config: dict[str, Any] = {"maxOutputTokens": req.max_tokens}
    if req.temperature is not None:
        config["temperature"] = req.temperature
    body: dict[str, Any] = {"contents": contents, "generationConfig": config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if req.tools:
        body["tools"] = [
            {
                "functionDeclarations": [
                    {"name": t.name, "description": t.description, "parameters": t.parameters}
                    for t in req.tools
                ]
            }
        ]
    return body


class GeminiAdapter(HttpAdapter):
    kind = "gemini"

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._require_key(), "content-type": "application/json"}

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        url = f"{self._base}/v1beta/models/{request.model}:streamGenerateContent?alt=sse"
        lines = self.lines("POST", url, headers=self._headers(), body=build_body(request))
        stop: str | None = None
        usage: Usage | None = None
        saw_call = False
        async for _event, data in sse(lines):
            chunk = parse_json(self._id, data)
            if "error" in chunk:
                raise ProviderError(ProviderErrorKind.SERVER, self._id, str(chunk["error"]))
            for cand in arr(chunk.get("candidates")):
                for part in arr(obj(cand.get("content")).get("parts")):
                    if "text" in part:
                        yield TextDelta(part["text"])
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        saw_call = True
                        # Gemini does not issue call ids; JARVIS assigns one.
                        yield ToolCallEvent(ToolCall(new_id(), fc["name"], obj(fc.get("args"))))
                if cand.get("finishReason"):
                    stop = cand["finishReason"]
            meta = chunk.get("usageMetadata")
            if meta:
                usage = Usage(
                    int(meta.get("promptTokenCount", 0)), int(meta.get("candidatesTokenCount", 0))
                )
        if stop is None:
            raise ProviderError(
                ProviderErrorKind.MALFORMED, self._id, "stream ended without a finish reason"
            )
        if stop in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
            raise ProviderError(
                ProviderErrorKind.BAD_REQUEST,
                self._id,
                f"response blocked by the provider ({stop})",
            )
        if usage:
            yield UsageEvent(usage)
        yield Done("tool_use" if saw_call else _STOP.get(stop, "other"))

    async def check(self) -> HealthResult:
        body = await self.get_json(f"{self._base}/v1beta/models", self._headers())
        models = tuple(str(m["name"]).removeprefix("models/") for m in body.get("models", []))
        return HealthResult(True, f"reachable; {len(models)} models listed", models)
