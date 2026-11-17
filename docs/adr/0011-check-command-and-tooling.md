# ADR-0011: Check command and tooling choices

**Status:** Accepted (2026-11-17)

## Decision
- **Check command:** `pnpm check` → `scripts/check.sh` (bash, `set -euo pipefail`). Avoids adding
  `just` (not pre-approved, not installed); pnpm is already required.
- **Python type checker:** pyright (strict for `backend/`), installed as a Python dev dependency.
- **Secret scan:** an in-repo scanner (`scripts/secret_scan.py`, stdlib only) over tracked files
  with patterns for common key formats (OpenAI/Anthropic/Google/AWS/GitHub/private keys) and an
  allowlist for the test canary `sk-test-JARVIS-CANARY` in test files only. gitleaks would add a
  non-pre-approved binary; can be adopted later via ADR if needed.
- **Formatting:** ruff format (Python), prettier via ESLint config or standalone (TS) — decided in
  M1 with a one-line DEVELOPMENT.md entry if prettier is added; `cargo fmt` (Rust).

## Consequences
- A homegrown scanner has narrower coverage than gitleaks; acceptable for a single-dev repo with
  pre-commit discipline, revisitable.
