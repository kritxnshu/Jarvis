"""ASGI middleware: every request must carry the per-launch secret."""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Callable

from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("jarvis.api.auth")


class LaunchSecretMiddleware:
    def __init__(
        self, app: ASGIApp, secret: str, on_reject: Callable[[str, str], None] | None = None
    ) -> None:
        self._app = app
        self._expected = b"Bearer " + secret.encode("ascii")
        self._on_reject = on_reject

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._app(scope, receive, send)
            return
        if scope["type"] != "http":
            return  # No websockets or other protocols are served.
        provided = b""
        for name, value in scope["headers"]:
            if name == b"authorization":
                provided = value
                break
        if hmac.compare_digest(provided, self._expected):
            await self._app(scope, receive, send)
            return
        reason = "missing" if not provided else "invalid"
        path = str(scope.get("path", ""))
        log.warning(
            "rejected request without valid launch secret", extra={"reason": reason, "path": path}
        )
        if self._on_reject is not None:
            self._on_reject(reason, path)
        body = json.dumps(
            {"error": {"code": "unauthorized", "message": "missing or invalid launch secret"}}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
