"""BRIEF §4.3 — provider switching, fallback, and API keys that never leak.
(Adapter contract tests against fixtures: tests/unit/test_provider_contracts.py.)"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.effect_server import EffectLog
from tests.fixtures.model_server import ModelServerState
from tests.support.backend import launch_backend, launch_fixture_backend
from tests.support.chat import ask, configure_local_models, route, wait_finished

FAKE_KEY = "sk-ant-api03-FAKEKEYFORTESTS-0123456789abcdef"  # secret-scan: allow


def test_switching_providers_mid_conversation_keeps_it_working(
    tmp_path: Path, effects: tuple[str, EffectLog], models: tuple[str, ModelServerState]
) -> None:
    url, state = models
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c:
            configure_local_models(c, url)
            route(c, ("ollama", "llama3.2"))
            cid = c.post("/v1/conversations", json={}).json()["id"]
            first = wait_finished(c, cid, ask(c, cid, "first question"))
            route(c, ("openai", "local-model"))  # switch mid-conversation
            second = wait_finished(c, cid, ask(c, cid, "second question"))
    finally:
        b.stop()
    assert (first["status"], first["provider_id"]) == ("complete", "ollama")
    assert (second["status"], second["provider_id"]) == ("complete", "openai")
    openai_call = next(r for r in state.requests if r["path"] == "/v1/chat/completions")
    history = json.dumps(openai_call["body"]["messages"])
    assert "first question" in history  # the new provider received the whole conversation
    assert "Hello, Priya." in history
    assert "second question" in history


def test_fallback_on_provider_failure_is_used_and_audited(
    tmp_path: Path, effects: tuple[str, EffectLog], models: tuple[str, ModelServerState]
) -> None:
    url, state = models
    state.ollama_status = 503  # simulated provider failure
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c:
            configure_local_models(c, url)
            route(c, ("ollama", "llama3.2"), ("openai", "local-model"))
            cid = c.post("/v1/conversations", json={}).json()["id"]
            reply = wait_finished(c, cid, ask(c, cid, "hello?"))
            fallbacks = c.post(
                "/v1/audit/search", json={"type_prefix": "provider.fallback"}
            ).json()["entries"]
    finally:
        b.stop()
    assert reply["status"] == "complete"
    assert reply["provider_id"] == "openai"
    [entry] = fallbacks
    assert entry["payload"]["from"] == "ollama/llama3.2"
    assert entry["payload"]["to"] == "openai/local-model"
    assert entry["payload"]["reason"] == "server"


def test_saved_key_is_masked_and_never_stored_or_exported(
    tmp_path: Path, effects: tuple[str, EffectLog]
) -> None:
    data = tmp_path / "data"
    b = launch_fixture_backend(data, effects[0])
    try:
        with b.client() as c:
            saved = c.put("/v1/providers/anthropic/credential", json={"secret": FAKE_KEY})
            listed = c.get("/v1/providers").text
            exports = [c.get(f"/v1/audit/export/{f}").text for f in ("json", "csv")]
            audit = c.post("/v1/audit/search", json={"limit": 1000}).text
    finally:
        b.stop()
    assert saved.status_code == 200
    assert saved.json()["credential_hint"] == "••••cdef"
    assert saved.json()["configured"] is True
    for text in (saved.text, listed, audit, *exports):
        assert FAKE_KEY not in text
    for f in data.rglob("*"):
        if f.is_file():
            assert FAKE_KEY.encode() not in f.read_bytes(), f


def test_health_check_reports_not_configured_and_reachable(
    tmp_path: Path, effects: tuple[str, EffectLog], models: tuple[str, ModelServerState]
) -> None:
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c:
            missing = c.post("/v1/providers/gemini/check").json()
            configure_local_models(c, models[0])
            ok = c.post("/v1/providers/ollama/check").json()
    finally:
        b.stop()
    assert missing == {
        "ok": False,
        "detail": "Not configured",
        "models": [],
        "error_kind": "not_configured",
    }
    assert ok["ok"] is True
    assert ok["models"] == ["llama3.2"]


@pytest.mark.skipif(sys.platform == "darwin", reason="would write to the real macOS Keychain")
def test_without_an_os_keychain_keys_are_refused_not_stored_elsewhere(tmp_path: Path) -> None:
    b = launch_backend(tmp_path / "data")  # production entry point: real KeychainSecretStore
    try:
        with b.client() as c:
            r = c.put("/v1/providers/anthropic/credential", json={"secret": FAKE_KEY})
            provider = next(
                p for p in c.get("/v1/providers").json()["providers"] if p["id"] == "anthropic"
            )
    finally:
        b.stop()
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "keychain_unavailable"
    assert provider["has_credential"] is False


@pytest.mark.macos
def test_keys_go_to_the_macos_keychain(tmp_path: Path) -> None:
    """macOS only: the production backend stores the key in the login Keychain.

    Only the item's attributes are read (no `-w`): reading the secret from another process
    would raise a Keychain access prompt, which nobody can answer on a CI machine.
    """
    b = launch_backend(tmp_path / "data")
    account = "provider:anthropic:api_key"
    find = ["security", "find-generic-password", "-s", "ai.jarvis.desktop", "-a", account]
    try:
        with b.client(timeout=30) as c:
            r = c.put("/v1/providers/anthropic/credential", json={"secret": FAKE_KEY})
            assert r.status_code == 200, r.text
            assert r.json()["credential_hint"] == "••••cdef"
            found = subprocess.run(find, capture_output=True, text=True, timeout=20, check=False)
            assert found.returncode == 0, found.stderr
            assert FAKE_KEY not in found.stdout
            removed = c.post("/v1/providers/anthropic/credential/delete")
            assert removed.json()["has_credential"] is False
    finally:
        b.stop()
        subprocess.run(
            ["security", "delete-generic-password", "-s", "ai.jarvis.desktop", "-a", account],
            capture_output=True,
            timeout=20,
            check=False,
        )
    gone = subprocess.run(find, capture_output=True, timeout=20, check=False)
    assert gone.returncode != 0
