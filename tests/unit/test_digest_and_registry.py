from __future__ import annotations

import math

import pytest

from jarvis.execution.digest import action_digest, canonical_json
from jarvis.tools.contract import Recovery, Risk
from jarvis.tools.registry import ToolContractError, ToolRegistry, build_production_registry
from tests.fixtures.tools import FIXTURE_TOOLS, EchoTool, ReconcilableEffect


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 1, "a": [1, {"y": 2, "x": 1}]}) == canonical_json(
        {"a": [1, {"x": 1, "y": 2}], "b": 1}
    )
    with pytest.raises(ValueError, match="JSON compliant"):
        canonical_json({"x": math.nan})


@pytest.mark.parametrize(
    "change",
    [
        {"tool": "other"},
        {"tool_version": 2},
        {"params": {"to": "b@example.com", "body": "hi"}},
        {"params": {"to": "a@example.com", "body": "hi "}},
        {"scope": "x"},
    ],
)
def test_any_change_changes_the_digest(change: dict[str, object]) -> None:
    base: dict[str, object] = {
        "tool": "t",
        "tool_version": 1,
        "params": {"to": "a@example.com", "body": "hi"},
        "scope": "",
    }
    changed = {**base, **change}
    assert action_digest(**base) != action_digest(**changed)  # type: ignore[arg-type]


def test_production_registry_contains_no_test_tools() -> None:
    names = build_production_registry().names()
    assert not [n for n in names if n.startswith("fixture.")]
    fixture_names = {cls.name for cls in FIXTURE_TOOLS}
    assert not fixture_names & set(names)


def test_registry_enforces_the_contract() -> None:
    class NoRecovery(ReconcilableEffect):
        name = "x.no_recovery"
        recovery = None

    class FakeIdempotent(ReconcilableEffect):
        name = "x.fake_idempotent"
        recovery = Recovery.IDEMPOTENT

    class HighestWithoutCategory(EchoTool):
        name = "x.highest"
        risk = Risk.HIGHEST

    reg = ToolRegistry()
    reg.register(EchoTool())
    with pytest.raises(ToolContractError, match="already registered"):
        reg.register(EchoTool())
    for bad in (NoRecovery(), FakeIdempotent(), HighestWithoutCategory()):
        with pytest.raises(ToolContractError):
            reg.register(bad)
