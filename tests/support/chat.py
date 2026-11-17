"""Helpers for driving conversations through the real backend API."""

from __future__ import annotations

import time
from typing import Any

import httpx


def configure_local_models(c: httpx.Client, url: str) -> None:
    """Point the free local providers at the fixture model server."""
    assert c.put("/v1/providers/ollama", json={"base_url": url}).status_code == 200
    r = c.put("/v1/providers/openai", json={"base_url": f"{url}/v1", "key_optional": True})
    assert r.status_code == 200


def route(c: httpx.Client, *steps: tuple[str, str]) -> None:
    chain = [{"provider_id": p, "model": m} for p, m in steps]
    assert c.put("/v1/routes/chat", json={"chain": chain}).status_code == 200


def message(c: httpx.Client, cid: str, mid: str) -> dict[str, Any]:
    msgs = c.get(f"/v1/conversations/{cid}/messages").json()["messages"]
    return next(m for m in msgs if m["id"] == mid)


def wait_finished(c: httpx.Client, cid: str, mid: str, timeout: float = 10) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        m = message(c, cid, mid)
        if m["status"] != "streaming":
            return m
        time.sleep(0.05)
    raise AssertionError("response never finished")


def ask(c: httpx.Client, cid: str, text: str) -> str:
    r = c.post(f"/v1/conversations/{cid}/messages", json={"text": text})
    assert r.status_code == 200, r.text
    return str(r.json()["message_id"])
