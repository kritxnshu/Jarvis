"""A local stand-in for model providers, speaking the real Ollama and OpenAI wire formats so the
real adapters run end to end. Test harness only; never part of a build."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class ModelServerState:
    tokens: list[str] = field(default_factory=lambda: ["Hello", ", ", "Priya", "."])
    delay_s: float = 0.0
    ollama_status: int = 200  # e.g. 503 to force a fallback
    requests: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, path: str, body: dict[str, Any]) -> None:
        with self.lock:
            self.requests.append({"path": path, "body": body})


def _handler(state: ModelServerState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream(self, ctype: str, chunks: list[bytes]) -> None:
            self.send_response(200)
            self.send_header("content-type", ctype)
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            try:
                for chunk in chunks:
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
                    time.sleep(state.delay_s)
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # the client stopped reading (e.g. the user pressed Stop)

        def do_GET(self) -> None:
            if self.path == "/api/tags":
                self._send(
                    200, json.dumps({"models": [{"name": "llama3.2"}]}).encode(), "application/json"
                )
            else:
                self._send(
                    200, json.dumps({"data": [{"id": "local-model"}]}).encode(), "application/json"
                )

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            state.record(self.path, body)
            if self.path == "/api/chat":
                if state.ollama_status != 200:
                    self._send(
                        state.ollama_status, b'{"error":"model overloaded"}', "application/json"
                    )
                    return
                lines = [
                    json.dumps(
                        {"message": {"role": "assistant", "content": t}, "done": False}
                    ).encode()
                    + b"\n"
                    for t in state.tokens
                ]
                lines.append(
                    json.dumps(
                        {
                            "message": {"role": "assistant", "content": ""},
                            "done": True,
                            "done_reason": "stop",
                            "prompt_eval_count": 3,
                            "eval_count": 4,
                        }
                    ).encode()
                    + b"\n"
                )
                self._stream("application/x-ndjson", lines)
            elif self.path == "/v1/chat/completions":
                events = [
                    b"data: "
                    + json.dumps(
                        {"choices": [{"index": 0, "delta": {"content": t}, "finish_reason": None}]}
                    ).encode()
                    + b"\n\n"
                    for t in state.tokens
                ]
                events.append(
                    b"data: "
                    + json.dumps(
                        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                    ).encode()
                    + b"\n\n"
                )
                events.append(b"data: [DONE]\n\n")
                self._stream("text/event-stream", events)
            else:
                self._send(404, b"{}", "application/json")

    return Handler


@contextmanager
def model_server() -> Generator[tuple[str, ModelServerState]]:
    state = ModelServerState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", state
    finally:
        server.shutdown()
        server.server_close()
