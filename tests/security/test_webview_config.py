"""BRIEF §5.2 webview hardening, checked against the real configuration files.

The runtime half (a remote script actually failing to load inside WKWebView) needs the macOS
app and is listed in IMPLEMENTATION_STATUS.md as awaiting manual verification.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
DESKTOP = REPO / "apps" / "desktop"
TAURI = DESKTOP / "src-tauri"

ALLOWED_COMMANDS = {"backend_status", "backend_request", "subscribe_events"}


def _conf() -> dict[str, Any]:
    return json.loads((TAURI / "tauri.conf.json").read_text())


def _csp() -> dict[str, str]:
    return _conf()["app"]["security"]["csp"]


def test_production_csp_allows_only_bundled_scripts() -> None:
    csp = _csp()
    assert csp["default-src"] == "'self'"
    assert csp["script-src"] == "'self'"
    assert csp["object-src"] == "'none'"
    assert csp["base-uri"] == "'none'"
    for directive, value in csp.items():
        assert "'unsafe-eval'" not in value, directive
        assert "'unsafe-inline'" not in value, directive
        assert "*" not in value.split(), directive


@pytest.mark.parametrize("directive", ["default-src", "script-src", "style-src", "font-src"])
def test_no_remote_origins_for_code_or_styles(directive: str) -> None:
    value = _csp()[directive]
    assert not re.search(r"https?:|wss?:|data:|blob:", value), f"{directive}: {value}"


def test_connect_src_is_ipc_only() -> None:
    assert set(_csp()["connect-src"].split()) == {"ipc:", "http://ipc.localhost"}


def test_no_global_tauri_and_frozen_prototype() -> None:
    security = _conf()["app"]["security"]
    assert _conf()["app"]["withGlobalTauri"] is False
    assert security["freezePrototype"] is True
    assert security.get("dangerousDisableAssetCspModification") in (None, False)
    assert security["capabilities"] == ["main"]


def test_capabilities_grant_only_the_jarvis_commands() -> None:
    files = list((TAURI / "capabilities").glob("*.json"))
    assert [f.name for f in files] == ["main.json"]
    cap = json.loads(files[0].read_text())
    assert cap["windows"] == ["main"]
    granted = set(cap["permissions"])
    expected = {"allow-" + c.replace("_", "-") for c in ALLOWED_COMMANDS}
    assert granted == expected, f"unexpected permissions: {granted ^ expected}"
    assert "remote" not in cap, "remote URLs must never get IPC access"


def test_declared_and_registered_commands_match_the_allowlist() -> None:
    build_rs = (TAURI / "build.rs").read_text()
    declared = set(re.findall(r'"([a-z_]+)"', build_rs.split(".commands(", 1)[1].split(")", 1)[0]))
    lib_rs = (TAURI / "src" / "lib.rs").read_text()
    handler = lib_rs.split("generate_handler![", 1)[1].split("]", 1)[0]
    registered = set(re.findall(r"commands::([a-z_]+)", handler))
    assert declared == ALLOWED_COMMANDS
    assert registered == ALLOWED_COMMANDS


def test_no_generic_tauri_plugins_linked_or_imported() -> None:
    cargo = (TAURI / "Cargo.toml").read_text()
    assert "tauri-plugin" not in cargo
    package = json.loads((DESKTOP / "package.json").read_text())
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert not [d for d in deps if d.startswith("@tauri-apps/plugin-")]


def test_frontend_never_handles_the_socket_or_secret() -> None:
    for path in (DESKTOP / "src").rglob("*.ts*"):
        text = path.read_text()
        assert "b.sock" not in text, path
        assert not re.search(r"authorization|launch.?secret", text, re.IGNORECASE), path
