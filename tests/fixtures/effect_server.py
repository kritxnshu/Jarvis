"""Local fixture server that records side effects, so tests can count them exactly.

POST /effect {"key", "mode"}: mode "record" stores an effect; "dedupe" stores it only once per
key (an idempotent API); "hang" stores it and then never answers (accepted, then hung).
GET /effects?key=K → {"count": n}. Test harness only; never part of a build.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


class EffectLog:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.effects: list[dict[str, Any]] = []
        self.requests: list[str] = []  # every POSTed key, including deduplicated repeats
        self.release = threading.Event()

    def count(self, key: str | None = None) -> int:
        with self.lock:
            return sum(1 for e in self.effects if key is None or e["key"] == key)


def _handler(log: EffectLog) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def _json(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            key = query.get("key", [None])[0]
            self._json(200, {"count": log.count(key)})

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            key, mode = str(body.get("key")), str(body.get("mode", "record"))
            with log.lock:
                log.requests.append(key)
                exists = any(e["key"] == key for e in log.effects)
                if not (mode == "dedupe" and exists):
                    log.effects.append({"key": key, "mode": mode, "at": time.time()})
            if mode == "hang":
                log.release.wait(60)
                return
            self._json(200, {"ok": True})

    return Handler


@contextmanager
def effect_server() -> Generator[tuple[str, EffectLog]]:
    log = EffectLog()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(log))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", log
    finally:
        log.release.set()
        server.shutdown()
        server.server_close()
