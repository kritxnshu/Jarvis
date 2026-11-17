"""Test harness: launch the real backend as a subprocess exactly as the Rust shell does."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class BackendProcess:
    proc: subprocess.Popen[bytes]
    secret: str
    socket_path: Path
    data_dir: Path
    ready: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def pid(self) -> int:
        return self.proc.pid

    def client(self, secret: str | None = None, timeout: float = 5.0) -> httpx.Client:
        token = self.secret if secret is None else secret
        headers = {"authorization": f"Bearer {token}"} if token else {}
        return httpx.Client(
            transport=httpx.HTTPTransport(uds=str(self.socket_path)),
            base_url="http://jarvis.local",
            headers=headers,
            timeout=timeout,
        )

    def close_stdin(self) -> None:
        stdin = self.proc.stdin
        if stdin is not None and not stdin.closed:
            stdin.close()

    def stop(self, timeout: float = 10.0) -> int:
        self.close_stdin()
        try:
            return self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return self.proc.wait(timeout)


def make_run_dir(base: Path) -> Path:
    run_dir = base / "run"
    run_dir.mkdir(exist_ok=True)
    run_dir.chmod(0o700)
    return run_dir


def _read_ready(stdout: IO[bytes], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    os.set_blocking(stdout.fileno(), False)
    buf = b""
    while time.monotonic() < deadline:
        chunk = stdout.read()
        if chunk:
            buf += chunk
            if b"\n" in buf:
                return json.loads(buf.split(b"\n", 1)[0])
        time.sleep(0.02)
    raise TimeoutError("backend did not report ready")


def launch_backend(
    data_dir: Path,
    secret: str | None = None,
    run_dir: Path | None = None,
    extra_env: dict[str, str] | None = None,
    ready_timeout: float = 15.0,
    command: list[str] | None = None,
) -> BackendProcess:
    secret = secret or secrets.token_hex(32)
    run_dir = run_dir or make_run_dir(data_dir.parent)
    socket_path = run_dir / "backend.sock"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **(extra_env or {})}
    proc = subprocess.Popen(
        command or [sys.executable, "-m", "jarvis"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**env, "PYTHONPATH": f"{REPO_ROOT / 'backend' / 'src'}:{REPO_ROOT}"},
        cwd=REPO_ROOT,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    handshake = {"secret": secret, "socket_path": str(socket_path), "data_dir": str(data_dir)}
    proc.stdin.write((json.dumps(handshake) + "\n").encode())
    proc.stdin.flush()
    backend = BackendProcess(proc, secret, socket_path, data_dir)
    try:
        backend.ready = _read_ready(proc.stdout, ready_timeout)
    except Exception:
        proc.kill()
        _out, err = proc.communicate(timeout=5)
        raise RuntimeError(f"backend failed to start: {err.decode(errors='replace')}") from None
    return backend


def wait_for_exit(proc: subprocess.Popen[bytes], timeout: float) -> int | None:
    try:
        return proc.wait(timeout)
    except subprocess.TimeoutExpired:
        return None


FIXTURE_BACKEND = [sys.executable, "-m", "tests.fixtures.backend_entry"]


def launch_fixture_backend(data_dir: Path, server_url: str) -> BackendProcess:
    """The real backend runtime with the test-only fixture tools registered."""
    return launch_backend(
        data_dir, command=FIXTURE_BACKEND, extra_env={"JARVIS_FIXTURE_SERVER": server_url}
    )
