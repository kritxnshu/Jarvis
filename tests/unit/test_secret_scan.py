from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.secret_scan import CANARY, scan


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    return tmp_path


def test_finds_planted_key(tmp_path: Path) -> None:
    key = "sk-" + "live" + "A1b2C3d4E5f6G7h8"
    findings = scan(_repo(tmp_path, {"config.py": f"KEY = '{key}'\n"}))
    assert len(findings) == 1
    assert findings[0].startswith("config.py:1")


@pytest.mark.parametrize(
    "text",
    [f"CANARY = '{CANARY}'\n", "k = 'sk-" + "liveA1b2C3d4E5f6' # secret-scan: allow\n", "plain\n"],
)
def test_allowed_content_passes(tmp_path: Path, text: str) -> None:
    assert scan(_repo(tmp_path, {"a.py": text})) == []


def test_ignored_files_are_not_scanned(tmp_path: Path) -> None:
    files = {".gitignore": "secret.env\n", "secret.env": "K=sk-" + "liveA1b2C3d4E5f6G7\n"}
    assert scan(_repo(tmp_path, files)) == []
