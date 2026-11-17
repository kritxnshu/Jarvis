"""Fail if anything that looks like a credential is in the working tree (tracked or new files).

Uses the same patterns as the runtime redactor. The test canary is always allowed; a line can
carry `secret-scan: allow` for deliberate fake fixtures.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from jarvis.trust.redaction import SECRET_PATTERNS

CANARY = "sk-test-JARVIS-CANARY"
ALLOW_MARK = "secret-scan: allow"
MAX_BYTES = 2_000_000


def candidate_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [root / p for p in out.stdout.decode().split("\0") if p]


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    for path in candidate_files(root):
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary
        for lineno, line in enumerate(text.splitlines(), 1):
            if ALLOW_MARK in line:
                continue
            cleaned = line.replace(CANARY, "")
            for pattern in SECRET_PATTERNS:
                if pattern.search(cleaned):
                    findings.append(
                        f"{path.relative_to(root)}:{lineno}: matches {pattern.pattern[:40]!r}"
                    )
        # Multi-line private keys.
        if "PRIVATE KEY-----" in text and ALLOW_MARK not in text:
            for pattern in SECRET_PATTERNS:
                if "PRIVATE KEY" in pattern.pattern and pattern.search(text):
                    findings.append(f"{path.relative_to(root)}: contains a private key block")
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = scan(root)
    for f in findings:
        print(f"secret-scan: {f}", file=sys.stderr)
    if findings:
        print(f"secret-scan: FAILED ({len(findings)} finding(s))", file=sys.stderr)
        return 1
    print("secret-scan: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
