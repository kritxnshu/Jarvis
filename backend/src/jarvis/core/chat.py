"""Streaming text conversation with stop control and persistence (BRIEF §4.1, text half)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from jarvis.clock import Clock, SystemClock, to_iso
from jarvis.core.routing import ModelRouter, RouteChosen
from jarvis.events import EventBus, EventEnvelope
from jarvis.ids import new_id
from jarvis.providers.types import (
    Done,
    Message,
    ProviderError,
    Role,
    TextDelta,
    UsageEvent,
)
from jarvis.storage.db import Database
from jarvis.trust.audit import AuditLog
from jarvis.trust.redaction import Redactor

log = logging.getLogger("jarvis.core.chat")

SYSTEM_PROMPT = (
    "You are JARVIS, a personal assistant on the user's Mac. Be concise and accurate. "
    "If you are not sure, say so. You cannot take actions on the computer in this version."
)
FLUSH_EVERY_S = 0.5


class ChatError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ChatMessage:
    id: str
    conversation_id: str
    role: str
    content: str
    status: str
    provider_id: str | None
    model: str | None
    error: str | None
    created_at: str


class ChatService:
    def __init__(
        self,
        db: Database,
        router: ModelRouter,
        bus: EventBus,
        audit: AuditLog,
        redactor: Redactor,
        clock: Clock | None = None,
    ) -> None:
        self._db = db
        self._router = router
        self._bus = bus
        self._audit = audit
        self._redactor = redactor
        self._clock = clock or SystemClock()
        self._running: dict[str, asyncio.Task[None]] = {}

    def _now(self) -> str:
        return to_iso(self._clock.now())

    # -- conversations ----------------------------------------------------------------------
    def create_conversation(self, title: str) -> str:
        cid, now = new_id(), self._now()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO conversations VALUES (?,?,?,?)",
                (cid, self._redactor.redact(title)[:200] or "New conversation", now, now),
            )
        return cid

    def conversations(self) -> list[dict[str, str]]:
        rows = self._db.query(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        return [dict(r) for r in rows]

    def messages(self, conversation_id: str) -> list[ChatMessage]:
        if not self._db.query("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)):
            raise ChatError("unknown_conversation", "no such conversation", 404)
        rows = self._db.query(
            "SELECT id, conversation_id, role, content, status, provider_id, model, error,"
            " created_at FROM messages WHERE conversation_id = ? ORDER BY created_at, rowid",
            (conversation_id,),
        )
        return [ChatMessage(*r) for r in rows]

    def mark_orphans_interrupted(self) -> int:
        """At startup: a message still 'streaming' was cut off by a crash or quit."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE messages SET status = 'interrupted', updated_at = ?,"
                " error = 'the app stopped while this response was streaming'"
                " WHERE status = 'streaming'",
                (self._now(),),
            )
        return cur.rowcount

    # -- sending ----------------------------------------------------------------------------
    async def send(self, conversation_id: str, text: str) -> tuple[str, str]:
        history = self.messages(conversation_id)
        if any(m.status == "streaming" for m in history):
            raise ChatError("busy", "a response is still streaming in this conversation", 409)
        user_id, reply_id, now = new_id(), new_id(), self._now()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, status,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (
                    user_id,
                    conversation_id,
                    "user",
                    self._redactor.redact(text),
                    "complete",
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, status,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (reply_id, conversation_id, "assistant", "", "streaming", now, now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
        prompt = (
            Message(Role.SYSTEM, SYSTEM_PROMPT),
            *[Message(Role(m.role), m.content) for m in history if m.content],
            Message(Role.USER, text),
        )
        task = asyncio.create_task(self._generate(conversation_id, reply_id, prompt))
        self._running[reply_id] = task
        task.add_done_callback(lambda _t: self._running.pop(reply_id, None))
        return user_id, reply_id

    async def stop(self, message_id: str) -> bool:
        task = self._running.get(message_id)
        if task is None:
            return False
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return True

    async def _generate(self, cid: str, mid: str, prompt: tuple[Message, ...]) -> None:
        parts: list[str] = []
        provider: str | None = None
        model: str | None = None
        usage: tuple[int, int] | None = None
        last_flush = asyncio.get_running_loop().time()
        status, error = "complete", None
        try:
            async for event in self._router.stream("chat", prompt):
                if isinstance(event, RouteChosen):
                    provider, model = event.provider_id, event.model
                    self._publish("chat.started", cid, mid, provider=provider, model=model)
                elif isinstance(event, TextDelta):
                    parts.append(event.text)
                    self._publish("chat.delta", cid, mid, text=event.text)
                    now = asyncio.get_running_loop().time()
                    if now - last_flush >= FLUSH_EVERY_S:
                        self._save(mid, "".join(parts), "streaming", provider, model, None, None)
                        last_flush = now
                elif isinstance(event, UsageEvent):
                    usage = (event.usage.input_tokens, event.usage.output_tokens)
                elif isinstance(event, Done) and event.stop_reason == "max_tokens":
                    error = "the response hit the length limit"
        except asyncio.CancelledError:
            status, error = "interrupted", "stopped by the user"
        except ProviderError as exc:
            status, error = "failed", f"{exc.kind.value}: {exc}"
        except Exception as exc:  # unexpected: record it rather than leave 'streaming' forever
            log.exception("chat generation crashed")
            status, error = "failed", f"internal error: {type(exc).__name__}"
        self._save(mid, "".join(parts), status, provider, model, error, usage)
        self._audit.append(
            "chat.response",
            {
                "conversation_id": cid,
                "message_id": mid,
                "status": status,
                "provider_id": provider,
                "model": model,
                "characters": len("".join(parts)),
            },
        )
        self._publish("chat.finished", cid, mid, status=status, error=error)

    def _save(
        self,
        mid: str,
        text: str,
        status: str,
        provider: str | None,
        model: str | None,
        error: str | None,
        usage: tuple[int, int] | None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE messages SET content = ?, status = ?, provider_id = ?, model = ?,"
                " error = ?, input_tokens = ?, output_tokens = ?, updated_at = ? WHERE id = ?",
                (
                    self._redactor.redact(text),
                    status,
                    provider,
                    model,
                    self._redactor.redact(error) if error else None,
                    usage[0] if usage else None,
                    usage[1] if usage else None,
                    self._now(),
                    mid,
                ),
            )

    def _publish(self, kind: str, cid: str, mid: str, **payload: object) -> None:
        self._bus.publish(
            EventEnvelope(type=kind, payload={"conversation_id": cid, "message_id": mid, **payload})
        )
