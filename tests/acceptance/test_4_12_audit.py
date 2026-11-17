"""BRIEF §4.12 — complete task history and audit logs, through the real backend."""

from __future__ import annotations

import signal
import sqlite3
from pathlib import Path

import httpx
import pytest

from jarvis.trust.approvals import native_confirmation_token
from jarvis.trust.audit import AUDIT_EVENT_TYPES
from tests.conftest import CANARY
from tests.fixtures.effect_server import EffectLog
from tests.support.backend import BackendProcess, launch_fixture_backend


def _task(c: httpx.Client, tool: str, params: dict[str, object] | None = None) -> dict[str, object]:
    r = c.post(
        "/v1/tasks", json={"tool": tool, "params": params or {}, "objective": f"audit run {CANARY}"}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _exercise_everything(b: BackendProcess, tmp_path: Path) -> None:
    with b.client(timeout=30) as c:  # retries of a hanging tool take a few seconds
        _task(c, "fixture.reconcilable")  # completed + verified
        _task(c, "fixture.reconcilable", {"mode": "hang"})  # uncertain → reconciled
        _task(c, "fixture.idempotent", {"mode": "hang"})  # failed (retried, then fails)
        _task(c, "fixture.liar")  # verification_failed
        _task(c, "fixture.no_check", {"text": "x"})  # unverifiable
        _task(c, "fixture.read_dir", {"path": str(tmp_path)})  # policy.denied
        manual = _task(c, "fixture.manual", {"mode": "hang"})  # needs review
        c.post(
            f"/v1/tasks/{manual['task_id']}/review",
            json={"action_id": manual["action_id"], "choice": "happened"},
        )  # user_attested
        rejected = _task(c, "fixture.consequential")
        c.post(f"/v1/approvals/{rejected['approval_id']}/decision", json={"approve": False})
        high = _task(c, "fixture.send_message", {"label": CANARY})
        c.post(f"/v1/approvals/{high['approval_id']}/decision", json={"approve": True})  # refused
        approval = c.get(f"/v1/approvals/{high['approval_id']}").json()
        token = native_confirmation_token(b.secret, approval["id"], approval["digest"])
        c.post(
            f"/v1/approvals/{approval['id']}/decision",
            json={"approve": True, "native_confirmation": token},
        )  # approved + runs
        grant = c.post(
            "/v1/grants", json={"scope_type": "directory", "scope_value": str(tmp_path)}
        ).json()
        c.post(f"/v1/grants/{grant['id']}/revoke")
        c.put("/v1/settings/appearance.reduced_motion", json={"value": "on"})
    with b.client(secret="f" * 64) as bad:
        assert bad.get(f"/v1/health?{CANARY}").status_code == 401  # auth.rejected


def test_every_event_type_appears_and_nothing_leaks(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    data = tmp_path / "data"
    marker = str(tmp_path / "crash.marker")
    first = launch_fixture_backend(data, effects[0])
    _exercise_everything(first, tmp_path)
    with first.client() as c, pytest.raises(httpx.TransportError):
        c.post(
            "/v1/tasks",
            json={
                "tool": "fixture.manual",
                "objective": "crash",
                "params": {"crash_before_effect": marker},
            },
        )
    assert first.proc.wait(10) == -signal.SIGKILL
    second = launch_fixture_backend(data, effects[0])  # recovery.started
    try:
        with second.client() as c:
            entries = c.post("/v1/audit/search", json={"limit": 1000}).json()["entries"]
            verify = c.get("/v1/audit/verify").json()
            exports = [c.get(f"/v1/audit/export/{f}").json()["content"] for f in ("json", "csv")]
    finally:
        second.stop()

    present = {e["type"] for e in entries}
    assert AUDIT_EVENT_TYPES - present == set(), "event types never logged"
    assert verify["ok"] is True
    assert verify["entries"] == len(entries)
    for text in exports:
        assert CANARY not in text
        assert first.secret not in text
    for f in data.rglob("*"):
        if f.is_file():
            blob = f.read_bytes()
            assert CANARY.encode() not in blob, f
            assert first.secret.encode() not in blob, f
            assert second.secret.encode() not in blob, f


def test_tampering_with_the_stored_log_is_detected(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    data = tmp_path / "data"
    first = launch_fixture_backend(data, effects[0])
    with first.client() as c:
        _task(c, "fixture.echo", {"text": "a"})
        assert c.get("/v1/audit/verify").json()["ok"] is True
    first.stop()
    conn = sqlite3.connect(data / "jarvis.sqlite3")
    conn.executescript(
        "DROP TRIGGER audit_log_no_update;"
        "UPDATE audit_log SET actor = 'someone-else' WHERE seq = 1;"
    )
    conn.close()
    second = launch_fixture_backend(data, effects[0])
    try:
        with second.client() as c:
            result = c.get("/v1/audit/verify").json()
    finally:
        second.stop()
    assert result["ok"] is False
    assert result["first_bad_seq"] == 1


def test_timeline_search_and_filters(tmp_path: Path, effects: tuple[str, EffectLog]) -> None:
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c:
            t = _task(c, "fixture.echo", {"text": "needle-123"})
            by_task = c.post("/v1/audit/search", json={"task_id": t["task_id"]}).json()["entries"]
            by_type = c.post("/v1/audit/search", json={"type_prefix": "action."}).json()["entries"]
            by_text = c.post("/v1/audit/search", json={"text": "needle-123"}).json()["entries"]
    finally:
        b.stop()
    assert by_task
    assert all(e["task_id"] == t["task_id"] for e in by_task)
    assert by_type
    assert all(e["type"].startswith("action.") for e in by_type)
    assert any("needle-123" in str(e["payload"]) for e in by_text)
