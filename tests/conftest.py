from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

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
