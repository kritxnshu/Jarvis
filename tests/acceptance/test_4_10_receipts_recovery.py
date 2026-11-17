"""BRIEF §4.10 (v0.1): single-action receipts, verification, and uncertain-action recovery."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import httpx
import pytest

from jarvis.execution.receipts import build_receipt
from jarvis.execution.states import ActionState, TaskState
from tests.fixtures.effect_server import EffectLog
from tests.support.backend import BackendProcess, launch_fixture_backend
from tests.support.kernel import kernel, run

# ------------------------------------------------------------------ verification honesty


def test_success_claim_that_fails_its_check_is_completed_not_verified(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    with kernel(tmp_path) as (s, _):
        r = run(s.executor.submit("fixture.liar", {}, "pretend"))
        receipt = build_receipt(s.store, r.task_id)
    assert r.action_state is ActionState.COMPLETED
    assert r.task_state is TaskState.NEEDS_REVIEW
    [action] = receipt["actions"]
    assert action["status_label"] == "Completed, not verified"
    assert action["verification"]["status"] == "failed"
    assert "verified" not in {a["state"] for a in receipt["actions"]}


def test_actions_without_a_check_say_so(tmp_path: Path, effects: tuple[str, EffectLog]) -> None:
    with kernel(tmp_path) as (s, _):
        r = run(s.executor.submit("fixture.no_check", {"text": "x"}, "x"))
        receipt = build_receipt(s.store, r.task_id)
    assert r.action_state is ActionState.UNVERIFIABLE
    assert receipt["actions"][0]["status_label"] == "Completed — no verification exists"
    assert receipt["final_status"] == "completed"


def test_receipt_holds_real_recorded_values(tmp_path: Path, effects: tuple[str, EffectLog]) -> None:
    with kernel(tmp_path) as (s, _):
        r = run(s.executor.submit("fixture.reconcilable", {"label": "z"}, "Record z"))
        receipt = build_receipt(s.store, r.task_id)
    [action] = receipt["actions"]
    [intent] = action["intents"]
    assert receipt["objective"] == "Record z"
    assert receipt["plan"] == [
        {"step": 1, "tool": "fixture.reconcilable", "parameters": action["parameters"]}
    ]
    assert action["state"] == "verified"
    assert intent["outcome"] == "completed"
    assert effects[1].requests == [intent["idempotency_key"]]  # the key the server really saw
    assert action["verification"]["evidence"] == {"effects_for_key": 1}
    assert receipt["outstanding_actions"] == []


# ------------------------------------------------------------------ timeouts


def test_timeout_after_the_effect_is_uncertain_then_reconciled_to_exactly_one_effect(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    with kernel(tmp_path) as (s, _):
        r = run(s.executor.submit("fixture.reconcilable", {"mode": "hang"}, "hangs"))
        types = [e.type for e in s.audit.list(task_id=r.task_id, limit=1000)]
    assert "action.uncertain" in types
    assert "action.failed" not in types
    assert "action.reconciled" in types
    assert r.action_state is ActionState.VERIFIED
    assert effects[1].count() == 1


def test_manual_tool_timeout_goes_to_needs_review_and_user_attestation(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    with kernel(tmp_path) as (s, _):
        r = run(s.executor.submit("fixture.manual", {"mode": "hang"}, "hangs"))
        assert r.task_state is TaskState.NEEDS_REVIEW
        assert r.action_state is ActionState.UNCERTAIN
        done = run(s.executor.resolve_review(r.action_id, "happened"))
        receipt = build_receipt(s.store, r.task_id)
    assert done.action_state is ActionState.USER_ATTESTED
    assert done.task_state is TaskState.COMPLETED
    assert receipt["actions"][0]["status_label"] == "User-attested (not verified)"
    assert effects[1].count() == 1  # never re-executed


def test_review_retry_goes_through_approval_again(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    with kernel(tmp_path) as (s, _):
        r = run(s.executor.submit("fixture.manual", {"mode": "hang"}, "hangs"))
        retry = run(s.executor.resolve_review(r.action_id, "retry"))
    assert retry.task_state is TaskState.WAITING_FOR_APPROVAL
    assert retry.approval_id is not None
    assert effects[1].count() == 1


# ------------------------------------------------------------------ crashes (real SIGKILL)


def _submit_and_crash(backend: BackendProcess, tool: str, params: dict[str, Any]) -> None:
    with backend.client() as c, pytest.raises(httpx.TransportError):
        c.post("/v1/tasks", json={"tool": tool, "params": params, "objective": "crash"})
    assert backend.proc.wait(10) == -signal.SIGKILL


def _only_task(backend: BackendProcess) -> dict[str, Any]:
    with backend.client() as c:
        [task] = c.get("/v1/tasks").json()["tasks"]
        return c.get(f"/v1/tasks/{task['id']}").json()


def test_crash_after_intent_manual_tool_goes_to_needs_review_without_rerun(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    data, marker = tmp_path / "data", str(tmp_path / "crash.marker")
    first = launch_fixture_backend(data, effects[0])
    _submit_and_crash(first, "fixture.manual", {"crash_before_effect": marker})
    second = launch_fixture_backend(data, effects[0])
    try:
        detail = _only_task(second)
    finally:
        second.stop()
    assert detail["task"]["state"] == "needs_review"
    action = detail["receipt"]["actions"][0]
    assert action["state"] == "uncertain"
    assert action["intents"][0]["outcome"] == "uncertain"
    assert effects[1].requests == []  # nothing ran, and nothing was re-run blindly


def test_crash_after_effect_reconcilable_is_resolved_with_exactly_one_effect(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    data, marker = tmp_path / "data", str(tmp_path / "crash.marker")
    first = launch_fixture_backend(data, effects[0])
    _submit_and_crash(first, "fixture.reconcilable", {"crash_after_effect": marker})
    second = launch_fixture_backend(data, effects[0])
    try:
        detail = _only_task(second)
    finally:
        second.stop()
    assert detail["task"]["state"] == "completed"
    assert detail["receipt"]["actions"][0]["state"] == "verified"
    assert effects[1].count() == 1
    assert len(effects[1].requests) == 1


def test_idempotent_rerun_after_crash_reuses_the_same_key(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    data, marker = tmp_path / "data", str(tmp_path / "crash.marker")
    first = launch_fixture_backend(data, effects[0])
    _submit_and_crash(first, "fixture.idempotent", {"crash_after_effect": marker})
    second = launch_fixture_backend(data, effects[0])
    try:
        detail = _only_task(second)
    finally:
        second.stop()
    keys = effects[1].requests
    assert len(keys) == 2
    assert keys[0] == keys[1]  # same idempotency key on the re-run
    assert effects[1].count() == 1  # the fixture server recorded exactly one effect
    assert detail["receipt"]["actions"][0]["state"] == "verified"


# ------------------------------------------------------------------ crash-safe local files

_WRITER = textwrap.dedent(
    """
    import os, signal, sys
    from pathlib import Path
    from jarvis.execution.atomic import atomic_write, safe_move
    def die():
        os.kill(os.getpid(), signal.SIGKILL)
    mode, a, b = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if mode == "write":
        atomic_write(a, b"NEW" * 100_000, before_replace=die)
    else:
        safe_move(a, b, force_copy=True, after_copy=die)
    """
)


def _crash(mode: str, a: Path, b: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-c", _WRITER, mode, str(a), str(b)],
        env={**os.environ, "PYTHONPATH": str(repo / "backend" / "src")},
        check=False,
    )
    assert proc.returncode == -signal.SIGKILL


def test_crash_during_write_leaves_the_original(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_bytes(b"OLD")
    _crash("write", target, tmp_path / "unused")
    assert target.read_bytes() == b"OLD"


def test_crash_during_cross_volume_move_leaves_a_complete_file(tmp_path: Path) -> None:
    src, dst = tmp_path / "a.bin", tmp_path / "moved.bin"
    payload = os.urandom(300_000)
    src.write_bytes(payload)
    _crash("move", src, dst)
    # Crash after the verified copy, before deleting the source: both are complete.
    assert dst.read_bytes() == payload
    assert src.read_bytes() == payload
    assert not [p for p in tmp_path.iterdir() if "jarvis-tmp" in p.name]
