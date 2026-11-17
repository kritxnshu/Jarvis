"""The real desktop app binary (BRIEF §5.2 M1 tests that need the Tauri process).

Runs only when JARVIS_DESKTOP_BINARY points at a built app binary (the check command sets it).
On Linux the window needs a display, so the binary is started under xvfb-run.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from tests.support.procs import alive, argv_and_env, children_of, inet_sockets_of

BINARY = os.environ.get("JARVIS_DESKTOP_BINARY", "")
pytestmark = pytest.mark.skipif(
    not BINARY, reason="JARVIS_DESKTOP_BINARY not set (run via the check command)"
)

HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


@dataclass
class RunningApp:
    launcher: subprocess.Popen[bytes]
    app_pid: int
    backend_pid: int
    data_dir: Path


def _descendants(pid: int) -> list[int]:
    found: list[int] = []
    frontier = [pid]
    while frontier:
        kids = children_of(frontier.pop())
        found.extend(kids)
        frontier.extend(kids)
    return found


def _cmdline(pid: int) -> str:
    out = subprocess.run(
        ["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True
    )
    return out.stdout.strip()


def _parent(pid: int) -> int:
    out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True)
    return int(out.stdout.strip() or 0)


@pytest.fixture
def app() -> Iterator[RunningApp]:
    # A short HOME: the socket path must stay under the 103-byte sun_path limit, and
    # pytest's own tmp_path is too deep for that.
    home = Path(tempfile.mkdtemp(prefix="jd-", dir="/tmp"))
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
    }
    argv = [BINARY]
    if sys.platform.startswith("linux"):
        xvfb = shutil.which("xvfb-run")
        if not xvfb:
            pytest.skip("xvfb-run not installed; the Linux webview needs a display")
        argv = [xvfb, "-a", BINARY]
    launcher = subprocess.Popen(
        argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )
    app_pid = backend_pid = 0
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not backend_pid:
        for pid in _descendants(launcher.pid):
            cmd = _cmdline(pid)
            if "-m jarvis" in cmd or "jarvis-backend" in cmd:
                backend_pid = pid
        time.sleep(0.2)
    if backend_pid:
        app_pid = _parent(backend_pid)  # the app spawns the backend directly
    try:
        assert backend_pid, "the app never started its backend"
        assert app_pid, "could not identify the app process"
        assert Path(BINARY).name in _cmdline(app_pid), "backend's parent is not the app"
        data_dirs = list(home.rglob("ai.jarvis.desktop"))
        assert data_dirs, "app data directory not created"
        yield RunningApp(launcher, app_pid, backend_pid, data_dirs[0])
    finally:
        # xvfb-run starts Xvfb outside our process group; kill every descendant explicitly.
        for pid in [*_descendants(launcher.pid), launcher.pid]:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        launcher.wait(10)
        shutil.rmtree(home, ignore_errors=True)


def _socket(app: RunningApp) -> Path:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        socks = list((app.data_dir / "run").glob("*/b.sock"))
        if socks:
            return socks[0]
        time.sleep(0.1)
    raise AssertionError("backend socket never appeared")


def test_app_starts_backend_on_private_socket(app: RunningApp) -> None:
    sock = _socket(app)
    assert sock.stat().st_mode & 0o777 == 0o600
    assert sock.parent.stat().st_mode & 0o777 == 0o700
    assert app.data_dir.stat().st_mode & 0o777 == 0o700
    assert children_of(app.app_pid).count(app.backend_pid) == 1


def test_no_tcp_or_udp_listeners_on_app_or_backend(app: RunningApp) -> None:
    _socket(app)
    assert inet_sockets_of(app.backend_pid) == []
    assert inet_sockets_of(app.app_pid) == []


def test_no_secret_in_process_listings(app: RunningApp) -> None:
    _socket(app)
    for pid in (app.app_pid, app.backend_pid):
        listing = argv_and_env(pid)
        assert not HEX64.search(listing), f"64-hex token visible in argv/env of pid {pid}"


def test_backend_rejects_requests_without_the_apps_secret(app: RunningApp) -> None:
    sock = _socket(app)
    with httpx.Client(transport=httpx.HTTPTransport(uds=str(sock)), base_url="http://j") as c:
        assert c.get("/v1/health").status_code == 401
        bad = {"authorization": "Bearer " + "f" * 64}
        assert c.get("/v1/settings", headers=bad).status_code == 401


def test_webview_requests_reach_the_backend(app: RunningApp) -> None:
    """The UI fetches health and settings on start; they must arrive via the Rust bridge."""
    log_file = app.data_dir / "logs" / "backend.jsonl"
    wanted = {("GET", "/v1/health", 200), ("GET", "/v1/settings", 200)}
    seen: set[tuple[str, str, int]] = set()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not wanted <= seen:
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                entry = json.loads(line)
                if entry.get("msg") == "request":
                    f = entry["fields"]
                    seen.add((f["method"], f["path"], f["status"]))
        time.sleep(0.2)
    assert wanted <= seen, f"backend saw only {sorted(seen)}"


def test_killing_the_app_stops_the_backend(app: RunningApp) -> None:
    _socket(app)
    os.kill(app.app_pid, signal.SIGKILL)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and alive(app.backend_pid):
        time.sleep(0.05)
    assert not alive(app.backend_pid), "backend survived the app being killed"
