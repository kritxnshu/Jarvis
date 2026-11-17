from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from jarvis.clock import to_iso
from jarvis.tools.contract import PermissionNeed, Risk
from jarvis.trust.policy import PolicyEngine, Verdict
from tests.support.kernel import kernel


def test_directory_grants_resolve_symlinks_and_traversal(tmp_path: Path) -> None:
    granted = tmp_path / "granted"
    (granted / "sub").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (granted / "escape").symlink_to(outside)
    with kernel(tmp_path) as (s, _):
        s.grants.add("directory", str(granted))
        engine = PolicyEngine(s.grants)

        def verdict(p: Path | str) -> Verdict:
            return engine.evaluate(Risk.READ_ONLY, [PermissionNeed("directory", str(p))]).verdict

        assert verdict(granted) is Verdict.ALLOW
        assert verdict(granted / "sub") is Verdict.ALLOW
        assert verdict(f"{granted}/sub/../../outside") is Verdict.DENY
        assert verdict(outside) is Verdict.DENY
        assert verdict(granted / "escape") is Verdict.DENY
        assert verdict(str(granted) + "-sibling") is Verdict.DENY


def test_expiry_and_revocation(tmp_path: Path) -> None:
    with kernel(tmp_path) as (s, clock):
        g = s.grants.add("domain", "example.com", to_iso(clock.now() + timedelta(minutes=5)))
        assert [x.id for x in s.grants.active()] == [g.id]
        clock.advance(minutes=6)
        assert s.grants.active() == []
        g2 = s.grants.add("tool", "fixture.echo")
        assert s.grants.revoke(g2.id)
        assert not s.grants.revoke(g2.id)
        assert s.grants.active() == []


def test_risk_drives_approval(tmp_path: Path) -> None:
    with kernel(tmp_path) as (s, _):
        engine = PolicyEngine(s.grants)
        assert engine.evaluate(Risk.LOW, []).verdict is Verdict.ALLOW
        assert engine.evaluate(Risk.CONSEQUENTIAL, []).verdict is Verdict.NEEDS_APPROVAL
        assert engine.evaluate(Risk.HIGHEST, []).verdict is Verdict.NEEDS_APPROVAL
        s.grants.add("domain", "example.com")
        need = [PermissionNeed("domain", "api.example.com")]
        assert engine.evaluate(Risk.LOW, need).verdict is Verdict.ALLOW
        assert (
            engine.evaluate(Risk.LOW, [PermissionNeed("domain", "evilexample.com")]).verdict
            is Verdict.DENY
        )
