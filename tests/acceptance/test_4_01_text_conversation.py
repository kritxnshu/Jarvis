"""BRIEF §4.1 (text, v0.1): streamed conversation persists across restarts; Stop ends a
response immediately and the partial text is saved, marked interrupted."""

from __future__ import annotations

import json
import signal
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.fixtures.effect_server import EffectLog
from tests.fixtures.model_server import ModelServerState
from tests.support.backend import launch_fixture_backend
from tests.support.chat import ask, configure_local_models, message, route, wait_finished


def test_streamed_conversation_persists_and_reloads_after_restart(
    tmp_path: Path, effects: tuple[str, EffectLog], models: tuple[str, ModelServerState]
) -> None:
    data = tmp_path / "data"
    first = launch_fixture_backend(data, effects[0])
    try:
        with first.client() as c:
            configure_local_models(c, models[0])
            route(c, ("ollama", "llama3.2"))
            cid = c.post("/v1/conversations", json={"title": "Greetings"}).json()["id"]
            mid = ask(c, cid, "Say hello to Priya")
            reply = wait_finished(c, cid, mid)
    finally:
        first.stop()
    assert reply["status"] == "complete"
    assert reply["content"] == "Hello, Priya."

    second = launch_fixture_backend(data, effects[0])  # full restart, new launch secret
    try:
        with second.client() as c:
            [conv] = c.get("/v1/conversations").json()["conversations"]
            msgs = c.get(f"/v1/conversations/{conv['id']}/messages").json()["messages"]
    finally:
        second.stop()
    assert conv["title"] == "Greetings"
    assert [(m["role"], m["content"], m["status"]) for m in msgs] == [
        ("user", "Say hello to Priya", "complete"),
        ("assistant", "Hello, Priya.", "complete"),
    ]
    assert msgs[1]["provider_id"] == "ollama"
    assert msgs[1]["model"] == "llama3.2"


def test_deltas_stream_over_the_event_channel(
    tmp_path: Path, effects: tuple[str, EffectLog], models: tuple[str, ModelServerState]
) -> None:
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c, b.client() as events, events.stream("GET", "/v1/events") as resp:
            lines = resp.iter_lines()
            assert json.loads(next(lines))["type"] == "system.stream_opened"
            configure_local_models(c, models[0])
            cid = c.post("/v1/conversations", json={}).json()["id"]
            ask(c, cid, "hi")
            seen: list[dict[str, Any]] = []
            while not seen or seen[-1]["type"] != "chat.finished":
                event = json.loads(next(lines))
                if str(event["type"]).startswith("chat."):
                    seen.append(event)
    finally:
        b.stop()
    deltas: list[str] = [e["payload"]["text"] for e in seen if e["type"] == "chat.delta"]
    assert "".join(deltas) == "Hello, Priya."
    assert len(deltas) == 4
    assert seen[0]["type"] == "chat.started"


def test_stop_ends_the_response_immediately_and_keeps_the_partial_text(
    tmp_path: Path, effects: tuple[str, EffectLog], models: tuple[str, ModelServerState]
) -> None:
    url, state = models
    state.tokens = [f"word{i} " for i in range(40)]
    state.delay_s = 0.1
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c:
            configure_local_models(c, url)
            cid = c.post("/v1/conversations", json={}).json()["id"]
            mid = ask(c, cid, "Count slowly")
            deadline = time.monotonic() + 10
            while "word2" not in message(c, cid, mid)["content"]:
                assert time.monotonic() < deadline, "no partial text was saved while streaming"
                time.sleep(0.05)
            started = time.monotonic()
            assert c.post(f"/v1/messages/{mid}/stop").json() == {"stopped": True}
            stop_latency = time.monotonic() - started
            stopped = message(c, cid, mid)
            time.sleep(0.6)  # tokens keep coming from the server; none may be appended
            later = message(c, cid, mid)
    finally:
        b.stop()
    assert stop_latency < 1.0
    assert stopped["status"] == "interrupted"
    assert stopped["content"].startswith("word0 word1 word2")
    assert len(stopped["content"].split()) < 40
    assert later["content"] == stopped["content"]
    assert later["status"] == "interrupted"


def test_a_crash_mid_stream_is_recorded_as_interrupted_not_complete(
    tmp_path: Path, effects: tuple[str, EffectLog], models: tuple[str, ModelServerState]
) -> None:
    url, state = models
    state.tokens = [f"w{i} " for i in range(60)]
    state.delay_s = 0.1
    data = tmp_path / "data"
    first = launch_fixture_backend(data, effects[0])
    with first.client() as c:
        configure_local_models(c, url)
        cid = c.post("/v1/conversations", json={}).json()["id"]
        mid = ask(c, cid, "long answer")
        time.sleep(1.2)  # let at least one periodic flush happen
    first.proc.send_signal(signal.SIGKILL)
    first.proc.wait(10)
    second = launch_fixture_backend(data, effects[0])
    try:
        with second.client() as c:
            m = message(c, cid, mid)
    finally:
        second.stop()
    assert m["status"] == "interrupted"
    assert m["content"].startswith("w0 ")


def test_unconfigured_route_fails_honestly(tmp_path: Path, effects: tuple[str, EffectLog]) -> None:
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c:
            route(c, ("anthropic", "claude-x"))  # no key saved
            cid = c.post("/v1/conversations", json={}).json()["id"]
            m = wait_finished(c, cid, ask(c, cid, "hi"))
    finally:
        b.stop()
    assert m["status"] == "failed"
    assert m["content"] == ""
    assert "not_configured" in m["error"]


@pytest.mark.parametrize("text", ["", "   ", "x" * 20_001])
def test_invalid_messages_are_rejected(
    tmp_path: Path, effects: tuple[str, EffectLog], text: str
) -> None:
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c:
            cid = c.post("/v1/conversations", json={}).json()["id"]
            r = c.post(f"/v1/conversations/{cid}/messages", json={"text": text})
    finally:
        b.stop()
    assert r.status_code == 422


def test_unknown_conversation_is_404(tmp_path: Path, effects: tuple[str, EffectLog]) -> None:
    b = launch_fixture_backend(tmp_path / "data", effects[0])
    try:
        with b.client() as c:
            r = c.post("/v1/conversations/NOPE/messages", json={"text": "hi"})
    finally:
        b.stop()
    assert r.status_code == 404
    assert isinstance(r, httpx.Response)
