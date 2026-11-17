# Implementation Status

Status vocabulary (BRIEF §3): Not started · In progress · Implemented · Tested · Verified ·
Tested — awaiting manual verification · Blocked.

"Tested" below means automated tests pass **on Linux** (this cloud session). Nothing has been run
on macOS yet, so nothing is Verified (ADR-0010).

_Last updated: 2026-11-17 (M1 built; awaiting macOS build and founder review)._

## Capabilities

No capability work has started: M1 is infrastructure. All twelve remain **Not started**.

| #    | Capability                                   | Release              | Status      | Evidence | Last verified | Blockers |
|------|----------------------------------------------|----------------------|-------------|----------|---------------|----------|
| 4.1  | Conversation — text                          | v0.1                 | Not started | —        | —             | —        |
| 4.1  | Conversation — voice                         | v0.3                 | Not started | —        | —             | —        |
| 4.2  | Persistent, editable personal memory         | v0.1                 | Not started | —        | —             | —        |
| 4.3  | Model provider switching                     | v0.1                 | Not started | —        | —             | Live smoke tests need a key or Ollama (contract tests use fixtures) |
| 4.4  | Browser navigation and automation            | v0.3                 | Not started | —        | —             | —        |
| 4.5  | Desktop observation with explicit permission | v0.3                 | Not started | —        | —             | —        |
| 4.6  | Authorized file search and management        | v0.1                 | Not started | —        | —             | —        |
| 4.7  | Controlled terminal execution                | v0.2                 | Not started | —        | —             | —        |
| 4.8  | Multi-step task planning                     | v0.2                 | Not started | —        | —             | —        |
| 4.9  | Background task persistence                  | v0.2                 | Not started | —        | —             | —        |
| 4.10 | Execution verification and receipts          | v0.1 / v0.2 / v0.3   | Not started | —        | —             | —        |
| 4.11 | Approval interface for consequential actions | v0.1                 | Not started | —        | —             | —        |
| 4.12 | Complete task history and audit logs         | v0.1                 | Not started | —        | —             | —        |

## M1 — Walking skeleton

Command for all evidence: `pnpm check` (last run 2026-11-17, Linux x86_64: all steps passed —
Python 84 passed; Vitest 38 passed; Rust 7 unit + 5 e2e passed; desktop app 6 passed; frozen sidecar 1 passed).

| Done-when item | Status | Evidence |
|---|---|---|
| App launches; a UI request round-trips through the bridge to the backend | Tested (Linux) | `tests/desktop/test_desktop_app.py::test_webview_requests_reach_the_backend` (real app, real webview under Xvfb: the UI's `GET /v1/health` and `GET /v1/settings` arrive with 200); `src-tauri/tests/bridge_e2e.rs::health_and_settings_round_trip_and_survive_restart`; screenshot of the running app showing "Core connected · core 0.1.0.dev0" |
| Settings survive a restart | Tested (Linux) | `tests/integration/test_backend_roundtrip.py::test_settings_survive_restart`, `bridge_e2e::health_and_settings_round_trip_and_survive_restart`, `test_frozen_sidecar.py`; UI: `App.test.tsx` "Preferences round trip" (fake bridge) |
| §5.2: no TCP/UDP port (lsof) | Tested (Linux, via /proc) | `test_backend_opens_no_tcp_or_udp_socket`, `test_no_tcp_or_udp_listeners_on_app_or_backend`. The macOS path uses `lsof` and has not run |
| §5.2: missing or wrong secret rejected | Tested (Linux) | `test_requests_without_valid_secret_are_rejected[missing,wrong,wrong-scheme,empty]`, `bridge_e2e::wrong_secret_is_rejected`, `test_backend_rejects_requests_without_the_apps_secret` |
| §5.2: secret not in argv/env of either process (ps) | Tested (Linux, via /proc) | `test_secret_not_in_process_arguments_or_environment`, `bridge_e2e::secret_is_not_in_backend_argv_or_environment`, `test_no_secret_in_process_listings` (both processes) |
| §5.2: killing the Tauri process makes the backend exit | Tested (Linux) | `test_killing_the_app_stops_the_backend` (SIGKILL on the real app; backend gone in < 5 s, observed 0.23 s manually), `test_backend_exits_when_parent_is_killed` |
| §5.2: webview can't load a remote script or call commands outside its allowlist | Tested (static config) — awaiting manual verification | `tests/security/test_webview_config.py` (11 tests: CSP, capabilities, registered commands, no plugins). Runtime proof inside WKWebView not automated; manual steps below |
| Settings persisted in SQLite with migrations | Tested | `tests/unit/test_migrator.py` (6), `tests/unit/test_settings_service.py` |
| Structured JSON logging with redaction | Tested | `tests/unit/test_redaction.py`, `test_launch_secret_and_canary_never_written_to_disk`, `test_requests_are_logged_without_bodies` |
| Check command | Tested | `pnpm check` green as above |
| Packaged macOS .app | **Not started on macOS** | Linux proxy only: frozen sidecar (`test_frozen_sidecar.py`) and a packaged debug build that launches it (manual run + desktop tests passed). CI job `macos` in `.github/workflows/ci.yml` builds the .app but has never run |

## Project facts (BRIEF §0)

| Fact | Value | Consequence until known |
|---|---|---|
| Repository | `kritxnshu/Jarvis`, started empty | — |
| Development machine | **Unknown** (founder travelling without the Mac) | macOS builds via CI; arm64 assumed |
| Model API keys | **Unknown** | Providers will show "Not configured" (M3) |
| Local models (Ollama) | **Unknown** | Ollama adapter will show "unreachable" |
| Voice provider accounts | **Unknown** | v0.3 |
| Apple Developer ID | **Unknown** | Unsigned/ad-hoc builds; Gatekeeper warns; no notarization |
| Cloud session | Linux x86_64 (Python 3.13.18, uv 0.11.32, Node 22.23.4, pnpm 10.28.0, Rust 1.97.0) | macOS-only steps can't run here |

## Manual verification steps for the founder (macOS)

1. On GitHub: Actions → **ci** → **Run workflow** on branch `claude/jarvis-macos-ai-os-aiyqsh`.
   The `macos` job runs `pnpm check` on macOS and uploads `JARVIS-macos-arm64.zip`.
2. On the Mac: unzip, then `xattr -dr com.apple.quarantine JARVIS.app` (it is unsigned), open it.
   Expect the status bar to say **Core connected** with a version.
3. Preferences → Motion → "Reduce motion"; quit (⌘Q) and reopen: the choice is kept.
4. In Terminal while it runs: `lsof -nP -a -p "$(pgrep -f JARVIS.app | paste -sd, -)" -i` prints nothing
   (no network sockets; WebKit helper processes are separate and not counted).
5. `ps -E -ww -o command= -p $(pgrep jarvis-backend)` shows no 64-character hex string.
6. `pkill -9 -f JARVIS.app/Contents/MacOS/`; within a few seconds `pgrep jarvis-backend` prints nothing.
7. Webview runtime check (needs a debug build: `pnpm --filter @jarvis/desktop dev`, then right-click →
   Inspect → Console): `await import("https://example.com/x.js")` must fail with a CSP error, and
   `window.__TAURI_INTERNALS__.invoke("plugin:shell|execute", {})` must be rejected as not allowed.

## Known limitations

- Peer-UID check on macOS (`LOCAL_PEERCRED`) is written but has never executed.
- The webview runtime CSP/command-allowlist check is static on Linux; step 7 above covers it.
- `sandbox-exec`, Keychain and code signing are not touched yet (later milestones).

## Current position

- **Release:** v0.1 — Trusted core
- **Milestone:** M1 — Walking skeleton — built and Tested on Linux; macOS build not yet run.
- **In progress:** nothing.

## Next step

Founder: run the macOS CI job (step 1 above) when convenient. Engineering: M2 — Trust kernel,
slice 1: tool contract (`jarvis/tools/contract.py`) + action digest (canonical JSON SHA-256) with tests,
then the executor with write-ahead intents (ADR-0005).
