from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.fixtures.effect_server import EffectLog, effect_server
from tests.fixtures.model_server import ModelServerState, model_server
from tests.fixtures.tools import SERVER_ENV
from tests.support.backend import BackendProcess, launch_backend

CANARY = "sk-test-JARVIS-CANARY"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if sys.platform == "darwin":
        return
    skip = pytest.mark.skip(reason="requires macOS (ADR-0010)")
    for item in items:
        if "macos" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def backend(tmp_path: Path) -> Iterator[BackendProcess]:
    proc = launch_backend(tmp_path / "data")
    try:
        yield proc
    finally:
        proc.stop()


@pytest.fixture
def effects(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, EffectLog]]:
    """A running fixture effect server, exported to fixture tools via the environment."""
    with effect_server() as (url, log):
        monkeypatch.setenv(SERVER_ENV, url)
        yield url, log


@pytest.fixture
def models() -> Iterator[tuple[str, ModelServerState]]:
    """A local server speaking the Ollama and OpenAI wire formats."""
    with model_server() as served:
        yield served
