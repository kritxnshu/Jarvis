"""Typed event envelope and an in-process bus that fans events out to stream subscribers."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from pydantic import BaseModel, Field

from jarvis import SCHEMA_VERSION
from jarvis.ids import new_id, utc_now_iso

log = logging.getLogger("jarvis.events")


class EventEnvelope(BaseModel):
    type: str
    id: str = Field(default_factory=new_id)
    ts: str = Field(default_factory=utc_now_iso)
    task_id: str | None = None
    schema_version: int = SCHEMA_VERSION
    payload: dict[str, Any] = Field(default_factory=dict)


_CLOSED = object()


class Subscription:
    def __init__(self, maxsize: int) -> None:
        self.queue: asyncio.Queue[EventEnvelope | object] = asyncio.Queue(maxsize=maxsize)
        self.overflowed = False

    async def next(self, timeout_s: float) -> EventEnvelope | None:
        """Next event, or None on timeout. Raises StopAsyncIteration when closed."""
        try:
            item = await asyncio.wait_for(self.queue.get(), timeout_s)
        except TimeoutError:
            return None
        if item is _CLOSED or not isinstance(item, EventEnvelope):
            raise StopAsyncIteration
        return item


class EventBus:
    """publish() may be called from any thread; delivery happens on the server's event loop."""

    def __init__(self, queue_size: int = 1000) -> None:
        self._queue_size = queue_size
        self._subs: set[Subscription] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> Subscription:
        sub = Subscription(self._queue_size)
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            self._subs.discard(sub)

    def publish(self, event: EventEnvelope) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            log.warning(
                "event dropped: bus not bound to a running loop", extra={"type": event.type}
            )
            return
        loop.call_soon_threadsafe(self._deliver, event)

    def close_all(self) -> None:
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            if not sub.queue.full():
                sub.queue.put_nowait(_CLOSED)

    def _deliver(self, event: EventEnvelope) -> None:
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                # A subscriber that can't keep up is disconnected rather than silently
                # missing events; the client reconnects and refetches state.
                sub.overflowed = True
                self.unsubscribe(sub)
                log.warning("event subscriber overflowed and was disconnected")
