"""The PyInstaller-frozen backend (ADR-0003) behaves like the source tree.

Runs only when JARVIS_FROZEN_SIDECAR points at dist-sidecar/jarvis-backend/jarvis-backend.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests.support.backend import launch_backend
from tests.support.procs import argv_and_env, inet_sockets_of

SIDECAR = os.environ.get("JARVIS_FROZEN_SIDECAR", "")
pytestmark = pytest.mark.skipif(
    not SIDECAR, reason="JARVIS_FROZEN_SIDECAR not set (build with scripts/build_sidecar.sh)"
)


def test_frozen_backend_round_trip_restart_and_exit(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = launch_backend(data, command=[SIDECAR], ready_timeout=60)
    try:
        assert inet_sockets_of(first.pid) == []
        assert first.secret not in argv_and_env(first.pid)
        with first.client() as c:
            assert c.get("/v1/health").json()["status"] == "ok"
            put = c.put("/v1/settings/appearance.reduced_motion", json={"value": "off"})
            assert put.status_code == 200
        with first.client(secret="0" * 64) as bad:
            assert bad.get("/v1/health").status_code == 401
    finally:
        started = time.monotonic()
        assert first.stop() == 0
        assert time.monotonic() - started < 5

    second = launch_backend(data, command=[SIDECAR], ready_timeout=60)
    try:
        with second.client() as c:
            values = {s["key"]: s["value"] for s in c.get("/v1/settings").json()["settings"]}
        assert values["appearance.reduced_motion"] == "off"
    finally:
        second.stop()
