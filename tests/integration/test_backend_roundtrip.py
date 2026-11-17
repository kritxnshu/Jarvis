"""The real backend process, reached over its Unix socket like the Rust bridge reaches it."""

from __future__ import annotations

import json
from pathlib import Path

from jarvis import SCHEMA_VERSION, __version__
from tests.support.backend import BackendProcess, launch_backend


def test_ready_line_and_health(backend: BackendProcess) -> None:
    assert backend.ready["ready"] is True
    assert backend.ready["pid"] == backend.pid
    with backend.client() as c:
        r = c.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": __version__, "schema_version": SCHEMA_VERSION}


def test_settings_survive_restart(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = launch_backend(data)
    try:
        with first.client() as c:
            r = c.put("/v1/settings/appearance.reduced_motion", json={"value": "on"})
            assert r.status_code == 200, r.text
            assert r.json()["value"] == "on"
    finally:
        assert first.stop() == 0

    second = launch_backend(data)  # new process, new secret, same data dir
    try:
        assert second.secret != first.secret
        with second.client() as c:
            settings = {s["key"]: s for s in c.get("/v1/settings").json()["settings"]}
        assert settings["appearance.reduced_motion"]["value"] == "on"
        assert settings["appearance.reduced_motion"]["is_default"] is False
    finally:
        second.stop()


def test_invalid_and_unknown_settings(backend: BackendProcess) -> None:
    with backend.client() as c:
        bad = c.put("/v1/settings/appearance.reduced_motion", json={"value": "sideways"})
        unknown = c.put("/v1/settings/does.not.exist", json={"value": 1})
        malformed = c.put("/v1/settings/appearance.reduced_motion", content=b"{not json")
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "invalid_setting_value"
    assert "sideways" not in bad.text
    assert unknown.status_code == 404
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "invalid_request"


def test_event_stream_delivers_setting_changes(backend: BackendProcess) -> None:
    with (
        backend.client() as stream_client,
        backend.client() as c,
        stream_client.stream("GET", "/v1/events") as resp,
    ):
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        lines = resp.iter_lines()
        opened = json.loads(next(lines))
        assert opened["type"] == "system.stream_opened"
        c.put("/v1/settings/appearance.show_status_bar", json={"value": False})
        event = json.loads(next(lines))
    assert event["type"] == "settings.changed"
    assert event["payload"] == {"key": "appearance.show_status_bar", "value": False}
    assert set(event) == {"type", "id", "ts", "task_id", "schema_version", "payload"}


def test_clean_exit_removes_socket(backend: BackendProcess) -> None:
    assert backend.socket_path.exists()
    assert backend.stop() == 0
    assert not backend.socket_path.exists()
