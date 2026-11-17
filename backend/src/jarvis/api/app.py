"""FastAPI application served on the Unix socket."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from jarvis import SCHEMA_VERSION, __version__
from jarvis.api.auth import LaunchSecretMiddleware
from jarvis.api.request_log import RequestLogMiddleware
from jarvis.api.schemas import (
    HealthResponse,
    Setting,
    SettingsResponse,
    SettingUpdate,
)
from jarvis.api.trust_routes import build_trust_router
from jarvis.config.settings_service import (
    InvalidSettingValueError,
    SettingsService,
    UnknownSettingError,
)
from jarvis.events import EventBus, EventEnvelope
from jarvis.execution.recovery import recover
from jarvis.services import Services

log = logging.getLogger("jarvis.api")


@dataclass
class AppDeps:
    secret: str
    services: Services
    heartbeat_s: float = 15.0
    recover_on_startup: bool = True

    @property
    def settings(self) -> SettingsService:
        return self.services.settings

    @property
    def bus(self) -> EventBus:
        return self.services.bus


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(deps: AppDeps) -> LaunchSecretMiddleware:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        deps.bus.bind_loop(asyncio.get_running_loop())
        if deps.recover_on_startup:
            summary = await recover(deps.services.executor)
            log.info("startup recovery finished", extra=summary)
        yield
        deps.bus.close_all()

    app = FastAPI(
        title="JARVIS core", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_req: Request, _exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default handler echoes the input; ours does not.
        return _error(422, "invalid_request", "request body failed validation")

    @app.get("/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__, schema_version=SCHEMA_VERSION)

    @app.get("/v1/settings", response_model=SettingsResponse)
    def list_settings() -> SettingsResponse:
        return SettingsResponse(settings=[Setting(**asdict(v)) for v in deps.settings.list()])

    @app.put("/v1/settings/{key}", response_model=Setting)
    def put_setting(key: str, body: SettingUpdate) -> Setting | JSONResponse:
        try:
            view = deps.settings.set(key, body.value)
        except UnknownSettingError:
            return _error(404, "unknown_setting", "no such setting")
        except InvalidSettingValueError as exc:
            return _error(422, "invalid_setting_value", str(exc))
        deps.services.audit.append(
            "settings.changed", {"key": key, "value": view.value}, actor="user"
        )
        deps.bus.publish(
            EventEnvelope(type="settings.changed", payload={"key": key, "value": view.value})
        )
        return Setting(**asdict(view))

    @app.get("/v1/events")
    async def events() -> StreamingResponse:
        sub = deps.bus.subscribe()

        async def stream() -> AsyncIterator[bytes]:
            try:
                yield _line(EventEnvelope(type="system.stream_opened"))
                while True:
                    try:
                        event = await sub.next(deps.heartbeat_s)
                    except StopAsyncIteration:
                        return
                    yield _line(event or EventEnvelope(type="system.heartbeat"))
            finally:
                deps.bus.unsubscribe(sub)

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    app.include_router(build_trust_router(deps.services))

    def on_reject(reason: str, path: str) -> None:
        deps.services.audit.append("auth.rejected", {"reason": reason, "path": path})

    # Auth runs first: unauthenticated requests are logged by the auth layer, not here.
    return LaunchSecretMiddleware(RequestLogMiddleware(app), deps.secret, on_reject)


def _line(event: EventEnvelope) -> bytes:
    return (json.dumps(event.model_dump(), separators=(",", ":")) + "\n").encode()
