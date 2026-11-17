"""BRIEF §5.2: nothing except the JARVIS app can reach the backend."""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn

from jarvis.runtime.protocol import make_peer_checked_protocol
from jarvis.runtime.uds import bind_unix_socket
from tests.conftest import CANARY
from tests.support.backend import BackendProcess, launch_backend, make_run_dir, wait_for_exit
from tests.support.procs import alive, argv_and_env, inet_sockets_of

# ---------------------------------------------------------------- no network listeners


def test_backend_opens_no_tcp_or_udp_socket(backend: BackendProcess) -> None:
    with backend.client() as c:  # exercise it first so any lazily opened socket would exist
        assert c.get("/v1/health").status_code == 200
    assert inet_sockets_of(backend.pid) == []


# ---------------------------------------------------------------- launch secret


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"authorization": "Bearer " + "0" * 64},
        {"authorization": "Basic Zm9vOmJhcg=="},
        {"authorization": "bearer"},
    ],
    ids=["missing", "wrong", "wrong-scheme", "empty"],
)
def test_requests_without_valid_secret_are_rejected(
    backend: BackendProcess, headers: dict[str, str]
) -> None:
    with httpx.Client(
        transport=httpx.HTTPTransport(uds=str(backend.socket_path)),
        base_url="http://jarvis.local",
        headers=headers,
    ) as c:
        for method, path in (("GET", "/v1/health"), ("GET", "/v1/settings"), ("GET", "/nope")):
            r = c.request(method, path)
            assert r.status_code == 401, (method, path)
            assert r.json()["error"]["code"] == "unauthorized"
        r = c.put("/v1/settings/appearance.reduced_motion", json={"value": "on"})
        assert r.status_code == 401
    with backend.client() as ok:
        current = {s["key"]: s["value"] for s in ok.get("/v1/settings").json()["settings"]}
    assert current["appearance.reduced_motion"] == "system"  # rejected write had no effect


def test_secret_in_query_string_is_not_accepted(backend: BackendProcess) -> None:
    with backend.client(secret="") as c:
        assert c.get("/v1/health", params={"token": backend.secret}).status_code == 401


def test_secret_not_in_process_arguments_or_environment(backend: BackendProcess) -> None:
    listing = argv_and_env(backend.pid)
    assert "jarvis" in listing  # sanity: we are looking at the right process
    assert backend.secret not in listing


# ---------------------------------------------------------------- lifecycle


def test_backend_exits_when_stdin_closes(backend: BackendProcess) -> None:
    started = time.monotonic()
    backend.close_stdin()
    code = wait_for_exit(backend.proc, timeout=5)
    assert code is not None, "backend still running 5s after its parent's pipe closed"
    assert time.monotonic() - started < 5
    assert code == 0


def test_backend_exits_when_parent_is_killed(tmp_path: Path) -> None:
    """Simulate the Tauri process dying: SIGKILL a parent that holds the stdin pipe."""
    script = tmp_path / "parent.py"
    pid_file = tmp_path / "child.pid"
    script.write_text(
        "import sys, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from pathlib import Path\n"
        "from tests.support.backend import launch_backend\n"
        "b = launch_backend(Path(sys.argv[2]))\n"
        "Path(sys.argv[3]).write_text(str(b.pid))\n"
        "time.sleep(60)\n"
    )
    repo = Path(__file__).resolve().parents[2]
    parent = subprocess.Popen(
        [sys.executable, str(script), str(repo), str(tmp_path / "data"), str(pid_file)],
        env={**os.environ, "PYTHONPATH": f"{repo}:{repo / 'backend' / 'src'}"},
    )
    try:
        deadline = time.monotonic() + 15
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert pid_file.exists(), "parent never launched the backend"
        child = int(pid_file.read_text())
        parent.kill()
        parent.wait(5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and alive(child):
            time.sleep(0.05)
        assert not alive(child), "backend survived its parent's death"
    finally:
        if parent.poll() is None:
            parent.kill()


def test_running_socket_is_private(backend: BackendProcess) -> None:
    assert backend.socket_path.stat().st_mode & 0o777 == 0o600
    assert backend.socket_path.parent.stat().st_mode & 0o777 == 0o700


def test_refuses_to_start_with_shared_socket_directory(tmp_path: Path) -> None:
    run_dir = make_run_dir(tmp_path)
    run_dir.chmod(0o755)
    with pytest.raises(RuntimeError, match="mode"):
        launch_backend(tmp_path / "data", run_dir=run_dir, ready_timeout=10)


# ---------------------------------------------------------------- peer UID check


@pytest.fixture
def foreign_uid_server(tmp_path: Path) -> Iterator[Path]:
    """A server that believes its owner is a different UID: every real peer is 'foreign'."""

    async def app(scope: dict[str, object], receive: object, send: object) -> None:
        raise AssertionError("request reached the app despite failing the peer check")

    run_dir = make_run_dir(tmp_path)
    path = run_dir / "peer.sock"
    sock = bind_unix_socket(path)
    config = uvicorn.Config(
        app, http=make_peer_checked_protocol(os.getuid() + 1), lifespan="off", log_config=None
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])))
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        yield path
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()


def test_connection_from_unexpected_uid_is_dropped(foreign_uid_server: Path) -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(str(foreign_uid_server))
    with contextlib.suppress(OSError):  # already closed by the server: also a rejection
        s.sendall(b"GET /v1/health HTTP/1.1\r\nhost: x\r\n\r\n")
    try:
        data = s.recv(1024)
    except ConnectionResetError:
        data = b""
    finally:
        s.close()
    assert data == b"", "server answered a peer with an unexpected UID"


# ---------------------------------------------------------------- secrets never persisted


def test_launch_secret_and_canary_never_written_to_disk(tmp_path: Path) -> None:
    b = launch_backend(tmp_path / "data")
    try:
        with b.client(secret=CANARY) as bad:
            assert bad.get("/v1/health").status_code == 401
        with b.client() as c:
            c.put("/v1/settings/appearance.reduced_motion", json={"value": CANARY})
            c.put(f"/v1/settings/{CANARY}", json={"value": CANARY})
            c.put(
                "/v1/settings/appearance.reduced_motion", content=f'{{"value": "{CANARY}'.encode()
            )
    finally:
        b.stop()
    _out, err = b.proc.communicate(timeout=5)
    written = [p for p in (tmp_path / "data").rglob("*") if p.is_file()]
    assert any(p.suffix == ".jsonl" for p in written), "expected a log file to inspect"
    assert any(p.name.startswith("jarvis.sqlite3") for p in written)
    for path in written:
        blob = path.read_bytes()
        assert b.secret.encode() not in blob, f"launch secret found in {path}"
        assert CANARY.encode() not in blob, f"canary found in {path}"
    assert b.secret.encode() not in err
    assert CANARY.encode() not in err
