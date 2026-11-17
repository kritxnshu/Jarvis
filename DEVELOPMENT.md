# Development

## Prerequisites

| Tool | Version used (2026-11-17) | Notes |
|---|---|---|
| macOS | 13+ target; founder's version unknown | builds and Verified status need macOS (ADR-0010) |
| Python | 3.13.18 (requires ≥3.12) | managed by uv |
| uv | 0.11.32 | |
| Node.js | 22.23.4 | |
| pnpm | 10.28.0 | pinned via `packageManager` |
| Rust | 1.97.0 stable | clippy, rustfmt |
| Linux only | libwebkit2gtk-4.1-dev, libayatana-appindicator3-dev, librsvg2-dev, xvfb | to compile Tauri and run the desktop tests headless |

## Setup

```bash
uv sync --all-groups          # Python deps (incl. dev + packaging groups)
pnpm install                  # JS deps for apps/desktop and packages/contracts
```

## Commands

| Command | What it does |
|---|---|
| `pnpm check` | **The check command** (`scripts/check.sh`): ruff format/lint, pyright strict, secret scan, pytest; prettier, ESLint, tsc, Vitest; contracts staleness; cargo fmt/clippy/test; builds the app with the embedded UI and runs the desktop process tests (Xvfb on Linux); freezes the sidecar and tests it. Steps that can't run print `SKIPPED (reason)`. |
| `pnpm --filter @jarvis/desktop dev` | run the app in dev mode (Vite dev server + development sidecar from `.venv`) |
| `pnpm --filter @jarvis/desktop build:app` | freeze the sidecar and build the release `.app` (macOS) with it bundled |
| `pnpm --filter @jarvis/desktop build:app:debug` | debug build, embedded UI, bundled frozen sidecar, no installer (any OS) |
| `./scripts/build_sidecar.sh` | PyInstaller `--onedir` freeze → `dist-sidecar/jarvis-backend/` |
| `pnpm --filter @jarvis/contracts generate` | regenerate TS types after changing API models |
| `uv run pytest tests/security` | one suite; desktop tests need `JARVIS_DESKTOP_BINARY=<path>` |

How the app finds its backend (`src-tauri/src/lib.rs`): a bundled `sidecar/jarvis-backend/jarvis-backend`
next to the resources wins; debug builds otherwise fall back to `<repo>/.venv/bin/python -m jarvis`.
Release builds have no fallback and show "Core failed to start" if the sidecar is missing.

CI: `.github/workflows/ci.yml` runs `pnpm check` on Linux for every push; the macOS job
(check + packaged `.app` artifact) runs on pull requests and manual dispatch.

## Dependency list

Pre-approved by the brief: Tauri 2, Rust, React, TypeScript, Vite, Tailwind CSS, Python, FastAPI,
Pydantic v2, uv, pnpm, SQLite, Playwright, pytest, Vitest, ruff, pyright, ESLint, tsc, clippy.

Versions in use: fastapi 0.163.1, pydantic 2.14.3, pytest 9.2.0, ruff 0.17.5, pyright 1.1.414;
tauri 2.12.6 (@tauri-apps/api + cli 2.12.5), react 19.3.1, vite 8.3.8, tailwindcss 4.3.5,
typescript 6.0.3 (7.x is not yet supported by typescript-eslint), eslint 10.15.0, vitest 5.1.0.

Additional dependencies and why:

| Dependency | Layer | Version | Justification |
|---|---|---|---|
| uvicorn | Python runtime | 0.54.0 | ASGI server for FastAPI; serves a pre-bound Unix socket and accepts a custom protocol class for the peer-UID check |
| h11 | Python runtime | 0.16.0 | (via uvicorn) pure-Python HTTP/1.1 parser; chosen over httptools to keep the frozen sidecar simple |
| httpx | Python runtime | 0.28.1 | provider adapters speak each vendor's HTTP API directly (ADR-0006); tests use it over the Unix socket |
| keyring | Python runtime | 25.7.0 | macOS Keychain access for API keys (ADR-0008); bundled with its metadata in the sidecar |
| pyinstaller | Python packaging | 6.22.3 | freezes the core into the sidecar (ADR-0003) |
| hyper, hyper-util, http-body-util, bytes | Rust | 1.12.0 / 0.1.21 / 0.1.5 / 1.12.1 | HTTP/1.1 client over `tokio::net::UnixStream` |
| tokio | Rust | 1.54.1 | process spawning, Unix sockets, timeouts (already used by Tauri) |
| serde, serde_json | Rust | 1.0.229 / 1.0.154 | bridge payloads (already used by Tauri) |
| getrandom | Rust | 0.3.4 | OS CSPRNG for the launch secret and run-dir id |
| tempfile | Rust dev | 3.27.0 | temporary directories in tests |
| hmac, sha2 | Rust | 0.12 / 0.10 | native-confirmation token (HMAC-SHA256), mirrors the Python backend (ADR-0004) |
| rfd | Rust | 0.15.4 | native macOS dialogs from Rust only (approval confirmation, audit export save); 0.16+ conflicts with Tauri's GTK on Linux |
| @tailwindcss/vite | TS dev | 4.3.5 | Tailwind v4's Vite integration |
| @vitejs/plugin-react | TS dev | 6.3.0 | React JSX/refresh for Vite |
| @eslint/js, typescript-eslint, eslint-plugin-react-hooks, globals | TS dev | 10.0.1 / 8.73.0 / 7.1.1 / 17.14.0 | ESLint configuration for strict type-checked TS and hooks rules |
| prettier | TS dev | 3.10.1 | TS/CSS/JSON formatting check |
| jsdom | TS dev | 31.0.1 | DOM for Vitest component tests |
| @testing-library/react, @testing-library/user-event | TS dev | 16.3.3 / 14.6.12 | component tests through accessible roles, like a user |
| @types/node, @types/react, @types/react-dom | TS dev | 26.6.6 / 19.3.0 / 19.3.0 | type definitions |
| json-schema-to-typescript | contracts dev | 16.0.0 | generates TS types from the backend's JSON Schema (ADR-0009) |

## Conventions

- Python: src layout under `backend/src/jarvis`, pyright strict, ruff (incl. bandit `S` rules).
- Tests: `tests/unit`, `tests/integration` (real backend subprocess), `tests/security`,
  `tests/desktop` (real app binary / frozen sidecar), `tests/acceptance` (one file per capability).
  Frontend tests sit next to the code (`*.test.ts[x]`); Rust unit tests in-module, e2e in `src-tauri/tests`.
- Fake secrets in fixtures carry `secret-scan: allow`; the canary `sk-test-JARVIS-CANARY` is always allowed.
- Commits: small, after a green `pnpm check`.
