"""Routes for model providers, routing and text conversation (M3)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from jarvis.api.schemas import (
    ChatMessageView,
    ConversationCreate,
    ConversationList,
    ConversationView,
    CredentialUpdate,
    HealthCheckView,
    MessageList,
    ProvidersResponse,
    ProviderUpdate,
    ProviderView,
    RouteStepView,
    RouteUpdate,
    SendMessage,
    SendResult,
    StopResult,
)
from jarvis.core.chat import ChatError
from jarvis.providers.registry import ProviderConfig, RouteStep, UnknownProviderError
from jarvis.providers.types import ProviderError
from jarvis.services import Services
from jarvis.trust.secrets import SecretStoreUnavailableError

MAX_MESSAGE_CHARS = 20_000


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _provider(cfg: ProviderConfig) -> ProviderView:
    return ProviderView(**asdict(cfg), configured=cfg.configured)


def build_chat_router(s: Services) -> APIRouter:
    router = APIRouter(prefix="/v1")

    def providers_view() -> ProvidersResponse:
        return ProvidersResponse(
            providers=[_provider(p) for p in s.providers.list()],
            routes={
                t: [RouteStepView(**asdict(step)) for step in chain]
                for t, chain in s.providers.routes().items()
            },
        )

    @router.get("/providers")
    def list_providers() -> ProvidersResponse:
        return providers_view()

    @router.put("/providers/{provider_id}")
    def update_provider(provider_id: str, body: ProviderUpdate) -> Any:
        try:
            return _provider(
                s.providers.update(
                    provider_id,
                    base_url=body.base_url,
                    enabled=body.enabled,
                    key_optional=body.key_optional,
                )
            )
        except UnknownProviderError:
            return _error(404, "unknown_provider", "no such provider")
        except ValueError as e:
            return _error(422, "invalid_provider_update", str(e))

    @router.put("/providers/{provider_id}/credential")
    def save_credential(provider_id: str, body: CredentialUpdate) -> Any:
        try:
            return _provider(s.providers.save_credential(provider_id, body.secret))
        except UnknownProviderError:
            return _error(404, "unknown_provider", "no such provider")
        except ValueError as e:
            return _error(422, "invalid_credential", str(e))
        except SecretStoreUnavailableError as e:
            return _error(503, "keychain_unavailable", str(e))

    @router.post("/providers/{provider_id}/credential/delete")
    def delete_credential(provider_id: str) -> Any:
        try:
            return _provider(s.providers.delete_credential(provider_id))
        except UnknownProviderError:
            return _error(404, "unknown_provider", "no such provider")
        except SecretStoreUnavailableError as e:
            return _error(503, "keychain_unavailable", str(e))

    @router.post("/providers/{provider_id}/check")
    async def check(provider_id: str) -> Any:
        try:
            cfg = s.providers.get(provider_id)
        except UnknownProviderError:
            return _error(404, "unknown_provider", "no such provider")
        if not cfg.configured:
            return HealthCheckView(
                ok=False, detail="Not configured", models=[], error_kind="not_configured"
            )
        try:
            result = await s.providers.adapter(provider_id).check()
        except ProviderError as e:
            return HealthCheckView(
                ok=False, detail=str(e)[:300], models=[], error_kind=e.kind.value
            )
        return HealthCheckView(
            ok=result.ok, detail=result.detail, models=list(result.models), error_kind=None
        )

    @router.put("/routes/{task}")
    def set_route(task: str, body: RouteUpdate) -> Any:
        try:
            s.providers.set_route(task, [RouteStep(x.provider_id, x.model) for x in body.chain])
        except UnknownProviderError:
            return _error(404, "unknown_provider", "no such provider")
        except ValueError as e:
            return _error(422, "invalid_route", str(e))
        return providers_view()

    @router.get("/conversations")
    def conversations() -> ConversationList:
        return ConversationList(
            conversations=[ConversationView(**c) for c in s.chat.conversations()]
        )

    @router.post("/conversations")
    def create(body: ConversationCreate) -> ConversationView:
        cid = s.chat.create_conversation(body.title)
        return next(ConversationView(**c) for c in s.chat.conversations() if c["id"] == cid)

    @router.get("/conversations/{conversation_id}/messages")
    def messages(conversation_id: str) -> Any:
        try:
            return MessageList(
                messages=[ChatMessageView(**asdict(m)) for m in s.chat.messages(conversation_id)]
            )
        except ChatError as e:
            return _error(e.status, e.code, str(e))

    @router.post("/conversations/{conversation_id}/messages")
    async def send(conversation_id: str, body: SendMessage) -> Any:
        text = body.text.strip()
        if not text or len(text) > MAX_MESSAGE_CHARS:
            return _error(422, "invalid_message", "message must be 1-20000 characters")
        try:
            user_id, reply_id = await s.chat.send(conversation_id, text)
        except ChatError as e:
            return _error(e.status, e.code, str(e))
        return SendResult(user_message_id=user_id, message_id=reply_id)

    @router.post("/messages/{message_id}/stop")
    async def stop(message_id: str) -> StopResult:
        return StopResult(stopped=await s.chat.stop(message_id))

    return router
