# Development

> **Status (M0):** no code exists yet. Commands below marked _(planned)_ arrive in M1.

## Prerequisites

| Tool | Planned minimum | Seen in cloud session (2026-11-17) |
|---|---|---|
| macOS | 14 Sonoma+ (founder's version unknown) | n/a (Linux container) |
| Xcode Command Line Tools | current | n/a |
| Python | 3.12+ (target 3.13) | 3.13.18 |
| uv | current stable | 0.11.32 |
| Node.js | 22 LTS | 22.23.4 |
| pnpm | 10.x | 10.28.0 |
| Rust (rustup) | stable | 1.97.0 |

Exact library versions are pinned in `uv.lock`, `pnpm-lock.yaml` and `Cargo.lock` once they
exist, and copied into the table in §4 when each dependency is added.

## Commands _(planned)_

| Command | What it does |
|---|---|
| `pnpm install && uv sync` | install JS and Python dependencies |
| `pnpm check` | **the check command**: format check, lint, type check, secret scan, all tests (Python, TS, Rust) via `scripts/check.sh` |
| `pnpm dev` | run the Tauri app in dev mode (macOS) |
| `pnpm build:app` | build the sidecar and the packaged `.app` (macOS) |
| `uv run pytest tests/acceptance -k 4_06` | run one capability's acceptance tests |
| `JARVIS_LIVE_SMOKE=1 uv run pytest tests/live` | opt-in live provider smoke tests (needs real keys) |

`scripts/check.sh` steps: `ruff format --check`, `ruff check`, `pyright`, `pytest`;
`eslint`, `tsc --noEmit`, `vitest run`, `prettier --check`(if adopted); `cargo fmt --check`,
`cargo clippy -D warnings`, `cargo test`; contract-staleness check; secret scan. Steps that
cannot run on the current OS (e.g. macOS-only tests on Linux) print an explicit `SKIPPED (reason)`
line — never a silent pass.

## Dependency list

Pre-approved by the brief (no justification needed): Tauri 2, Rust, React, TypeScript, Vite,
Tailwind CSS, Python 3.12+, FastAPI, Pydantic v2, uv, pnpm, SQLite, Playwright, pytest, Vitest,
ruff, pyright, ESLint, tsc, cargo clippy.

Additional dependencies (each needs a one-line justification when added; versions filled in when added):

| Dependency | Layer | Version | Justification | Added |
|---|---|---|---|---|
| _none yet_ | | | | |

Planned additions (proposed in ADRs, not yet added):
- `uvicorn` — ASGI server for FastAPI; supports Unix domain sockets (ADR-0002).
- `httpx` — HTTP client for provider adapters without vendor SDKs; `MockTransport` for recorded fixtures (ADR-0006).
- `PyInstaller` — freeze the Python core into a self-contained sidecar for the .app (ADR-0003).
- `keyring` — macOS Keychain access from Python behind `SecretStore` (ADR-0008).
- `json-schema-to-typescript` (dev) — generate TS contracts from Pydantic JSON Schema (ADR-0009).
- Rust: `tokio`, `hyper` + `hyper-util` (HTTP/1.1 over `UnixStream`), `serde`/`serde_json`,
  `rand`/`getrandom` (secret), `hmac` + `sha2` (native confirmation token), `tauri-plugin-dialog`
  used from Rust only.
- `sqlite-vec` — vector search inside SQLite (M4; ADR-0007).

## Conventions

- Python: src layout, `from __future__ import annotations`, pyright strict on `backend/`, ruff defaults + isort.
- Tests: `tests/unit`, `tests/integration`, `tests/security`, `tests/acceptance` (one file per
  capability, named `test_4_NN_<name>.py`), fixtures in `tests/fixtures`.
- Commits: small, after a green `pnpm check`, imperative subject line.
