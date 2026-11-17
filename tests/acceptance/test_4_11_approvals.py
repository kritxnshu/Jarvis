"""BRIEF §4.11 — approval interface for consequential actions (enforced in the backend)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from jarvis.execution.executor import ExecutionError
from jarvis.execution.states import ActionState, TaskState
from jarvis.trust.approvals import ApprovalError, native_confirmation_token
from tests.fixtures.effect_server import EffectLog
from tests.support.backend import BackendProcess, launch_fixture_backend
from tests.support.kernel import kernel, run


@pytest.fixture
def api(tmp_path: Path, effects: tuple[str, EffectLog]) -> Iterator[BackendProcess]:
    backend = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        yield backend
    finally:
        backend.stop()


def _audit_types(backend: BackendProcess) -> list[str]:
    with backend.client() as c:
        entries = c.post("/v1/audit/search", json={"limit": 1000}).json()["entries"]
    return [e["type"] for e in entries]


def test_consequential_action_waits_and_shows_what_why_service_data_consequences(
    api: BackendProcess, effects: tuple[str, EffectLog]
) -> None:
    with api.client() as c:
        r = c.post(
            "/v1/tasks",
            json={
                "tool": "fixture.consequential",
                "params": {"label": "invoice"},
                "objective": "Send it",
            },
        )
        body = r.json()
        assert body["task_state"] == "waiting_for_approval"
        pending = c.get("/v1/approvals").json()["approvals"]
    assert effects[1].count() == 0
    [approval] = pending
    for field in ("intent", "why", "service", "data_affected", "consequences", "parameters"):
        assert approval["request"][field], field
    assert "invoice" in approval["request"]["intent"]
    assert approval["highest_risk"] is False


def test_compromised_ui_cannot_approve_highest_risk_without_native_confirmation(
    api: BackendProcess, effects: tuple[str, EffectLog]
) -> None:
    """A request straight to the backend with the valid secret but no native confirmation."""
    with api.client() as c:
        task = c.post(
            "/v1/tasks",
            json={"tool": "fixture.send_message", "params": {}, "objective": "Message Priya"},
        ).json()
        approval_id = task["approval_id"]
        missing = c.post(f"/v1/approvals/{approval_id}/decision", json={"approve": True})
        forged = c.post(
            f"/v1/approvals/{approval_id}/decision",
            json={"approve": True, "native_confirmation": "0" * 64},
        )
        status = c.get(f"/v1/approvals/{approval_id}").json()["status"]
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "native_confirmation_required"
    assert forged.status_code == 403
    assert status == "pending"
    assert effects[1].count() == 0
    assert _audit_types(api).count("approval.refused") == 2


def test_native_confirmation_from_the_shell_approves_and_runs_once(
    api: BackendProcess, effects: tuple[str, EffectLog]
) -> None:
    with api.client() as c:
        task = c.post(
            "/v1/tasks",
            json={"tool": "fixture.send_message", "params": {}, "objective": "Message Priya"},
        ).json()
        approval = c.get(f"/v1/approvals/{task['approval_id']}").json()
        # Exactly what the Rust shell computes after the user clicks Approve in the dialog.
        token = native_confirmation_token(api.secret, approval["id"], approval["digest"])
        r = c.post(
            f"/v1/approvals/{approval['id']}/decision",
            json={"approve": True, "native_confirmation": token},
        )
        assert r.status_code == 200, r.text
        assert r.json()["action_state"] == "verified"
        replay = c.post(
            f"/v1/approvals/{approval['id']}/decision",
            json={"approve": True, "native_confirmation": token},
        )
    assert replay.status_code == 403
    assert replay.json()["error"]["code"] == "approval_not_pending"
    assert effects[1].count() == 1


def test_rejecting_means_it_never_runs(api: BackendProcess, effects: tuple[str, EffectLog]) -> None:
    with api.client() as c:
        task = c.post(
            "/v1/tasks", json={"tool": "fixture.consequential", "params": {}, "objective": "x"}
        ).json()
        r = c.post(f"/v1/approvals/{task['approval_id']}/decision", json={"approve": False})
    assert r.json()["task_state"] == "cancelled"
    assert r.json()["action_state"] == "rejected"
    assert effects[1].count() == 0
    assert "approval.rejected" in _audit_types(api)


def test_changing_any_parameter_after_approval_invalidates_it(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    with kernel(tmp_path) as (s, _):
        r = run(s.executor.submit("fixture.consequential", {"label": "a"}, "x"))
        assert r.approval_id is not None
        s.approvals.decide(r.approval_id, True, None, r.task_id)
        with s.db.transaction() as conn:  # the plan is altered after the user approved it
            conn.execute(
                "UPDATE actions SET params_json = ? WHERE id = ?",
                (
                    '{"label": "b", "mode": "record", "crash_before_effect": null,'
                    ' "crash_after_effect": null}',
                    r.action_id,
                ),
            )
        with pytest.raises(ExecutionError) as info:
            run(s.executor.run(r.action_id, r.approval_id))
        assert info.value.code == "approval_digest_mismatch"
        assert effects[1].count() == 0
        assert [e.payload["code"] for e in s.audit.list(type_prefix="approval.refused")] == [
            "approval_digest_mismatch"
        ]


def test_approvals_cannot_be_replayed(tmp_path: Path, effects: tuple[str, EffectLog]) -> None:
    with kernel(tmp_path) as (s, _):
        r = run(s.executor.submit("fixture.consequential", {}, "x"))
        assert r.approval_id is not None
        done = run(s.executor.decide(r.approval_id, True, None))
        assert done.action_state is ActionState.VERIFIED
        with pytest.raises(ExecutionError) as info:
            run(s.executor.run(r.action_id, r.approval_id))
        assert info.value.code == "approval_replayed"
        assert effects[1].count() == 1


def test_expired_approvals_are_refused(tmp_path: Path, effects: tuple[str, EffectLog]) -> None:
    with kernel(tmp_path) as (s, clock):
        r = run(s.executor.submit("fixture.consequential", {}, "x"))
        assert r.approval_id is not None
        clock.advance(minutes=11)
        with pytest.raises(ApprovalError) as info:
            run(s.executor.decide(r.approval_id, True, None))
        assert info.value.code == "approval_expired"
        # Approved in time, but consumed after expiry, is refused too.
        r2 = run(s.executor.submit("fixture.consequential", {}, "y"))
        assert r2.approval_id is not None
        s.approvals.decide(r2.approval_id, True, None, r2.task_id)
        clock.advance(minutes=11)
        with pytest.raises(ExecutionError) as info2:
            run(s.executor.run(r2.action_id, r2.approval_id))
        assert info2.value.code == "approval_expired"
        assert effects[1].count() == 0
        assert s.store.task(r.task_id).state is TaskState.WAITING_FOR_APPROVAL  # type: ignore[union-attr]


def test_no_route_creates_or_grants_an_approval_from_model_output(api: BackendProcess) -> None:
    """The only approval routes are list/get/decide; creation exists only in the executor."""
    with api.client() as c:
        assert c.post("/v1/approvals", json={"action_id": "x"}).status_code in (404, 405)
        assert c.put("/v1/approvals/x", json={"status": "approved"}).status_code in (404, 405)
        assert (
            c.post(
                "/v1/tasks",
                json={
                    "tool": "fixture.consequential",
                    "params": {},
                    "objective": "x",
                    "approval_id": "a",
                },
            ).json()["task_state"]
            == "waiting_for_approval"
        )
