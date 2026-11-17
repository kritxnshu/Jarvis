"""Test-only tools. Registered only by tests and tests/fixtures/backend_entry.py — never by
jarvis.tools.registry.build_production_registry (asserted by a security test)."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import urllib.request
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from jarvis.tools.contract import (
    ApprovalCategory,
    ApprovalText,
    ExecContext,
    PermissionNeed,
    ReconcileOutcome,
    Reconciliation,
    Recovery,
    Risk,
    Tool,
    Verification,
    VerificationStatus,
)
from jarvis.tools.registry import ToolRegistry

SERVER_ENV = "JARVIS_FIXTURE_SERVER"


def _server() -> str:
    return os.environ[SERVER_ENV]


def _post(key: str, mode: str) -> None:
    req = urllib.request.Request(  # noqa: S310 - local fixture server only
        _server() + "/effect",
        data=json.dumps({"key": key, "mode": mode}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    # Short timeout: a hung request must not outlive the test (tool timeouts are 2 s).
    with urllib.request.urlopen(req, timeout=4) as resp:  # noqa: S310
        resp.read()


def _count(key: str) -> int:
    with urllib.request.urlopen(f"{_server()}/effects?key={key}", timeout=5) as resp:  # noqa: S310
        return int(json.loads(resp.read())["count"])


def _maybe_crash(marker: str | None) -> None:
    """Crash this process once (SIGKILL) if the marker file does not exist yet."""
    if marker and not Path(marker).exists():
        Path(marker).write_text("crashed")
        os.kill(os.getpid(), signal.SIGKILL)


class EffectIn(BaseModel):
    label: str = "effect"
    mode: str = "record"  # record | hang
    crash_before_effect: str | None = None  # marker file path
    crash_after_effect: str | None = None


class EffectOut(BaseModel):
    key: str


class _EffectTool(Tool[EffectIn, EffectOut]):
    input_model = EffectIn
    output_model = EffectOut
    post_mode: ClassVar[str] = "record"

    async def execute(self, inp: EffectIn, ctx: ExecContext) -> EffectOut:
        _maybe_crash(inp.crash_before_effect)
        mode = "hang" if inp.mode == "hang" else self.post_mode
        await asyncio.to_thread(_post, ctx.idempotency_key, mode)
        _maybe_crash(inp.crash_after_effect)
        return EffectOut(key=ctx.idempotency_key)

    async def verify(self, inp: EffectIn, out: EffectOut, ctx: ExecContext) -> Verification:
        n = await asyncio.to_thread(_count, ctx.idempotency_key)
        status = VerificationStatus.VERIFIED if n == 1 else VerificationStatus.FAILED
        return Verification(status, {"effects_for_key": n})

    async def reconcile(self, inp: EffectIn, ctx: ExecContext) -> Reconciliation:
        n = await asyncio.to_thread(_count, ctx.idempotency_key)
        if n > 0:
            return Reconciliation(
                ReconcileOutcome.HAPPENED,
                {"effects_for_key": n, "output": {"key": ctx.idempotency_key}},
            )
        return Reconciliation(ReconcileOutcome.NOT_HAPPENED, {"effects_for_key": 0})


class ReconcilableEffect(_EffectTool):
    name = "fixture.reconcilable"
    risk = Risk.LOW
    recovery = Recovery.RECONCILABLE
    timeout_s = 2.0


class IdempotentEffect(_EffectTool):
    name = "fixture.idempotent"
    risk = Risk.LOW
    idempotent = True
    recovery = Recovery.IDEMPOTENT
    post_mode = "dedupe"
    timeout_s = 2.0


class ManualEffect(_EffectTool):
    name = "fixture.manual"
    risk = Risk.LOW
    recovery = Recovery.MANUAL
    timeout_s = 2.0

    async def reconcile(self, inp: EffectIn, ctx: ExecContext) -> Reconciliation:
        raise AssertionError("manual tools are never reconciled")


class ConsequentialEffect(_EffectTool):
    name = "fixture.consequential"
    risk = Risk.CONSEQUENTIAL
    category = ApprovalCategory.EXTERNAL_ACTION
    recovery = Recovery.RECONCILABLE
    timeout_s = 2.0

    def describe(self, inp: EffectIn) -> ApprovalText:
        return ApprovalText(
            intent=f"Record a fixture effect labelled {inp.label!r}",
            why="Acceptance test of the approval flow.",
            service="Local fixture server",
            data_affected="One fixture effect record",
            consequences="A counter on the local fixture server increases by one.",
        )


class SendMessageEffect(ConsequentialEffect):
    name = "fixture.send_message"
    risk = Risk.HIGHEST
    category = ApprovalCategory.SEND_MESSAGE


class LiarIn(BaseModel):
    note: str = ""


class LiarOut(BaseModel):
    ok: bool


class LiarTool(Tool[LiarIn, LiarOut]):
    """Reports success without doing anything; its independent check therefore fails."""

    name = "fixture.liar"
    input_model = LiarIn
    output_model = LiarOut
    risk = Risk.LOW
    recovery = Recovery.MANUAL

    async def execute(self, inp: LiarIn, ctx: ExecContext) -> LiarOut:
        return LiarOut(ok=True)

    async def verify(self, inp: LiarIn, out: LiarOut, ctx: ExecContext) -> Verification:
        n = await asyncio.to_thread(_count, ctx.idempotency_key)
        return Verification(VerificationStatus.FAILED, {"effects_for_key": n})


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    text: str


class EchoTool(Tool[EchoIn, EchoOut]):
    name = "fixture.echo"
    input_model = EchoIn
    output_model = EchoOut
    risk = Risk.READ_ONLY
    side_effects = False

    async def execute(self, inp: EchoIn, ctx: ExecContext) -> EchoOut:
        return EchoOut(text=inp.text)

    async def verify(self, inp: EchoIn, out: EchoOut, ctx: ExecContext) -> Verification:
        ok = out.text == inp.text
        return Verification(VerificationStatus.VERIFIED if ok else VerificationStatus.FAILED)


class NoCheckTool(EchoTool):
    name = "fixture.no_check"

    async def verify(self, inp: EchoIn, out: EchoOut, ctx: ExecContext) -> Verification:
        return Verification(VerificationStatus.UNVERIFIABLE, {"reason": "nothing to check"})


class DirIn(BaseModel):
    path: str


class DirectoryReader(Tool[DirIn, EchoOut]):
    name = "fixture.read_dir"
    input_model = DirIn
    output_model = EchoOut
    risk = Risk.READ_ONLY
    side_effects = False

    def permissions(self, inp: DirIn) -> list[PermissionNeed]:
        return [PermissionNeed("directory", inp.path)]

    async def execute(self, inp: DirIn, ctx: ExecContext) -> EchoOut:
        return EchoOut(text=",".join(sorted(os.listdir(inp.path))))

    async def verify(self, inp: DirIn, out: EchoOut, ctx: ExecContext) -> Verification:
        return Verification(VerificationStatus.VERIFIED)


FIXTURE_TOOLS = (
    ReconcilableEffect,
    IdempotentEffect,
    ManualEffect,
    ConsequentialEffect,
    SendMessageEffect,
    LiarTool,
    EchoTool,
    NoCheckTool,
    DirectoryReader,
)


def build_fixture_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for cls in FIXTURE_TOOLS:
        registry.register(cls())
    return registry
