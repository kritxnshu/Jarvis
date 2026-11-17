# Implementation Status

Status vocabulary (BRIEF §3): Not started · In progress · Implemented · Tested · Verified ·
Tested — awaiting manual verification · Blocked.

"Tested" means automated tests pass in this cloud session (Linux) **and** the macOS CI job's
`pnpm check` step passed (GitHub Actions, macos-15, run 44089303217, commit b2db164). Per-test
counts on macOS could not be read from here (the log host is blocked by the session proxy); the
workflow now prints a summary as its last step. Nothing is **Verified** until run on a real Mac by
a person where the brief needs it.

_Last updated: 2026-11-17 (end of M2)._

## Capabilities

| #    | Capability                                   | Release | Status | Evidence (all via `pnpm check`) | Last run | Blockers |
|------|----------------------------------------------|---------|--------|----------------------------------|----------|----------|
| 4.1  | Conversation — text                          | v0.1 | Not started | — | — | — |
| 4.1  | Conversation — voice                         | v0.3 | Not started | — | — | — |
| 4.2  | Persistent, editable personal memory         | v0.1 | Not started | — | — | — |
| 4.3  | Model provider switching                     | v0.1 | Not started | — | — | Live smoke tests need a key or Ollama |
| 4.4  | Browser navigation and automation            | v0.3 | Not started | — | — | — |
| 4.5  | Desktop observation                          | v0.3 | Not started | — | — | — |
| 4.6  | Authorized file search and management        | v0.1 | Not started | (directory grants + path resolution exist: `tests/unit/test_policy.py`) | — | — |
| 4.7  | Controlled terminal execution                | v0.2 | Not started | — | — | — |
| 4.8  | Multi-step task planning                     | v0.2 | Not started | — | — | — |
| 4.9  | Background task persistence                  | v0.2 | In progress | Transition tables tested exhaustively (`tests/unit/test_states.py`, 222 cases: every task and action state pair plus invariants); restart rule Running→Paused("interrupted") in `execution/recovery.py`, exercised by the crash tests | 2026-11-17 | Queue/checkpoints/resume are M7 |
| 4.10 | Receipts & uncertain-action recovery (v0.1 part) | v0.1 | Tested | `tests/acceptance/test_4_10_receipts_recovery.py` (11): completed-not-verified, unverifiable label, real recorded values, timeout⇒Uncertain⇒reconciled with exactly one effect, manual⇒Needs review⇒user-attested, retry⇒approval, SIGKILL after intent (manual: no re-run; reconcilable: one effect; idempotent: same key, one effect), crash mid-write and mid cross-volume move. File-operation receipts (hashes) need the M5 file tool | 2026-11-17 | — |
| 4.11 | Approval interface | v0.1 | Tested — awaiting manual verification | `tests/acceptance/test_4_11_approvals.py` (8): compromised UI (valid secret, no/forged native token) refused + audited, native token path runs once, reject never runs, parameter change after approval refused, replay refused, expiry refused, no route creates approvals. Rust: `native_confirm::tests` (5, incl. cross-language token vector), `routes::tests::native_confirmation_never_passes_the_generic_bridge`. UI: `TrustScreens.test.tsx` | 2026-11-17 | The native macOS dialog must be clicked by a person (step 8 below) |
| 4.12 | Task history and audit logs | v0.1 | Tested | `tests/acceptance/test_4_12_audit.py` (3): every one of the 22 event types appears in one end-to-end run (incl. crash + recovery), chain verifies, tampering detected after restart, canary + launch secrets absent from DB/logs/exports; `tests/unit/test_audit.py` (11); timeline UI `TrustScreens.test.tsx` | 2026-11-17 | — |

## Milestones

| Milestone | State | Evidence |
|---|---|---|
| M1 — Walking skeleton | Done (manual Mac run pending) | Linux: desktop app under Xvfb (6 tests); macOS CI: `pnpm check` passed (incl. desktop app tests run on macOS) and `JARVIS-macos-arm64.zip` (22.8 MB, unsigned) built — artifact expires 2026-12-01 |
| M2 — Trust kernel | Done (native dialog awaiting manual verification) | see 4.10/4.11/4.12 above; last local `pnpm check`: Python 352 passed, Vitest 45 passed, Rust 14 unit + 5 e2e passed, desktop 6 passed, frozen sidecar 1 passed |

M1 details (each item Tested on Linux; covered by the macOS CI check run):
app launch + UI→Rust→backend round trip (`test_webview_requests_reach_the_backend`), settings survive
restart, no TCP/UDP listener, missing/wrong secret rejected, secret absent from argv/env of both
processes, backend exits when the app is SIGKILLed, strict CSP + 5-command capability
(`tests/security/test_webview_config.py`), JSON logging with redaction, frozen PyInstaller sidecar.

## Project facts (BRIEF §0)

| Fact | Value | Consequence until known |
|---|---|---|
| Repository | `kritxnshu/Jarvis`, started empty | — |
| Development machine | **Unknown**; founder travelling without the Mac | macOS evidence comes from CI (arm64 runner) |
| Model API keys | **Unknown** | Providers will show "Not configured" (M3) |
| Local models (Ollama) | **Unknown** | Ollama adapter will show "unreachable" |
| Apple Developer ID | **Unknown** | Unsigned build; Gatekeeper warns; no notarization |

## Manual verification steps for the founder (on a Mac)

1. GitHub → Actions → **ci** → the latest successful run → download **JARVIS-macos-arm64** (or Run
   workflow on branch `claude/jarvis-macos-ai-os-aiyqsh` to build a fresh one).
2. Unzip, run `xattr -dr com.apple.quarantine JARVIS.app` (unsigned build), open it. Expect the
   status bar to say **Core connected** with a version.
3. Preferences → Motion → "Reduce motion"; quit (⌘Q) and reopen: the choice is kept.
4. `lsof -nP -a -p "$(pgrep -f JARVIS.app | paste -sd, -)" -i` prints nothing.
5. `ps -E -ww -o command= -p $(pgrep jarvis-backend)` shows no 64-character hex string.
6. `pkill -9 -f JARVIS.app/Contents/MacOS/`; within a few seconds `pgrep jarvis-backend` prints nothing.
7. Dev build only (`pnpm --filter @jarvis/desktop dev`, right-click → Inspect → Console):
   `await import("https://example.com/x.js")` fails with a CSP error, and
   `window.__TAURI_INTERNALS__.invoke("plugin:shell|execute", {})` is rejected as not allowed.
8. Native confirmation dialog: needs a highest-risk tool, and production has none until later
   milestones. Dev-only way to see it: run the fixture backend (instructions to be added with the
   first real highest-risk tool). Until then 4.11 stays "awaiting manual verification".

## Known limitations

- The UI cannot start tasks yet (no production tools; `POST /v1/tasks` is not on the bridge allowlist).
- Approval expiry is fixed at 10 minutes (no "approval settings" UI yet).
- Orphaned `.jarvis-tmp` files from a crash mid-write are left in place (never mistaken for the
  real file); cleanup arrives with the file tool in M5.
- `sandbox-exec`, Keychain and code signing are not touched yet.

## Current position

- **Release:** v0.1 — Trusted core
- **Milestone:** M2 — Trust kernel — complete apart from the manual native-dialog check.
- **In progress:** nothing.

## Next step

M3 — Conversation and providers, slice 1: normalized model interface
(`jarvis/providers/types.py`: Message, ToolSpec, ToolCall, StreamDelta, Usage, ProviderError) and
the recorded-fixture contract-test harness (`httpx.MockTransport`), then the Anthropic adapter.
