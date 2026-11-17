# ADR-0001: Process model and stack

**Status:** Accepted (2026-11-17)

## Context
The brief (§5.1, §6) prescribes Tauri 2 + React/TS + a Python FastAPI sidecar. The repository
was empty, so there is no legacy stack to reconcile.

## Decision
- Three processes/layers: WebView (React/TS/Vite/Tailwind) → Rust shell (Tauri 2) → Python core.
- Monorepo: `apps/desktop` (Tauri + UI), `backend/src/jarvis` (Python), `packages/contracts`
  (generated types), root `tests/`. One root `pyproject.toml` (uv) and one pnpm workspace.
- The Rust shell spawns the sidecar itself with `tokio::process` (it needs a piped stdin for the
  secret and the liveness signal) rather than via `tauri-plugin-shell`, so no shell plugin is
  linked at all. The binary may still be bundled via Tauri's `externalBin`/resources.
- OS-specific Rust code lives behind a `platform` module with traits; macOS is the only impl.

## Consequences
- Business logic lives in Python; Rust stays thin (bridge, lifecycle, native UI, OS services).
- Two runtimes to package (see ADR-0003) — the main structural risk, proven in M1.
