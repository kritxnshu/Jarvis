#!/usr/bin/env bash
# The check command (`pnpm check`). Green is the bar for every commit.
# Steps that cannot run here print "SKIPPED (reason)" — never a silent pass.
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_NO_PROGRESS=1

step() { printf '\n=== %s\n' "$*"; }
skip() { printf '\n=== %s: SKIPPED (%s)\n' "$1" "$2"; }

step "python: ruff format --check"
uv run ruff format --check backend tests scripts
step "python: ruff check"
uv run ruff check backend tests scripts
step "python: pyright (strict)"
uv run pyright
step "secret scan"
uv run python scripts/secret_scan.py
step "python: pytest"
uv run pytest tests --ignore=tests/desktop

if [ -d apps/desktop ]; then
  step "ts: prettier --check"
  pnpm --filter @jarvis/desktop run format:check
  step "ts: eslint"
  pnpm --filter @jarvis/desktop run lint
  step "ts: tsc --noEmit"
  pnpm --filter @jarvis/desktop run typecheck
  step "ts: vitest"
  pnpm --filter @jarvis/desktop run test
else
  skip "typescript" "apps/desktop not created yet"
fi

if [ -d packages/contracts ]; then
  step "contracts: generated types are up to date"
  pnpm --filter @jarvis/contracts run check
else
  skip "contracts" "packages/contracts not created yet"
fi

if [ -f apps/desktop/src-tauri/Cargo.toml ]; then
  step "rust: cargo fmt --check"
  (cd apps/desktop/src-tauri && cargo fmt --check)
  step "rust: cargo clippy -D warnings"
  (cd apps/desktop/src-tauri && cargo clippy --all-targets --locked -- -D warnings)
  step "rust: cargo test"
  (cd apps/desktop/src-tauri && cargo test --locked)
  step "desktop app: build binary with the embedded frontend (development sidecar)"
  rm -rf apps/desktop/src-tauri/target/debug/sidecar  # never test a stale bundled sidecar
  (cd apps/desktop && pnpm exec tauri build --debug --no-bundle -- --locked)
  app_binary="$PWD/apps/desktop/src-tauri/target/debug/jarvis-desktop"
  if [ "$(uname)" = "Darwin" ] || command -v xvfb-run >/dev/null; then
    step "desktop app: process-level security tests"
    JARVIS_DESKTOP_BINARY="$app_binary" uv run pytest tests/desktop/test_desktop_app.py
  else
    skip "desktop app tests" "no display: install xvfb (Linux) or run on macOS"
  fi
else
  skip "rust" "apps/desktop/src-tauri not created yet"
fi

step "sidecar: freeze with PyInstaller and test the frozen backend"
./scripts/build_sidecar.sh >/dev/null
JARVIS_FROZEN_SIDECAR="$PWD/dist-sidecar/jarvis-backend/jarvis-backend" \
  uv run --group packaging pytest tests/desktop/test_frozen_sidecar.py

printf '\n=== check: all steps passed\n'
