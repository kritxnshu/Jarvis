"""Per-task model routing with ordered fallback (BRIEF §4.3). Every fallback is audited."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from jarvis.providers.registry import ProviderRegistry
from jarvis.providers.types import (
    ChatRequest,
    Message,
    ProviderError,
    ProviderErrorKind,
    StreamEvent,
    ToolSpec,
)
from jarvis.trust.audit import AuditLog


@dataclass(frozen=True)
class RouteChosen:
    provider_id: str
    model: str


class ModelRouter:
    def __init__(self, registry: ProviderRegistry, audit: AuditLog) -> None:
        self._registry = registry
        self._audit = audit

    async def stream(
        self,
        task: str,
        messages: tuple[Message, ...],
        tools: tuple[ToolSpec, ...] = (),
        max_tokens: int = 1024,
    ) -> AsyncIterator[RouteChosen | StreamEvent]:
        chain = self._registry.route(task)
        if not chain:
            raise ProviderError(
                ProviderErrorKind.NOT_CONFIGURED, "router", f"no model is configured for {task}"
            )
        last: ProviderError | None = None
        for index, step in enumerate(chain):
            cfg = self._registry.get(step.provider_id)
            started = False
            try:
                if not cfg.configured:
                    raise ProviderError(
                        ProviderErrorKind.NOT_CONFIGURED,
                        cfg.id,
                        f"{cfg.display_name} is not configured",
                    )
                adapter = self._registry.adapter(cfg.id)
                request = ChatRequest(step.model, messages, tools, max_tokens)
                async for event in adapter.stream(request):
                    if not started:
                        started = True
                        yield RouteChosen(cfg.id, step.model)
                    yield event
                return
            except ProviderError as err:
                if started:
                    raise  # output already reached the user: never silently switch mid-answer
                last = err
                if index + 1 < len(chain):
                    nxt = chain[index + 1]
                    self._audit.append(
                        "provider.fallback",
                        {
                            "task": task,
                            "from": f"{cfg.id}/{step.model}",
                            "to": f"{nxt.provider_id}/{nxt.model}",
                            "reason": err.kind.value,
                            "detail": str(err)[:300],
                        },
                    )
        assert last is not None
        raise last
