# Roadmap

Milestones and their Done-when criteria are defined in [docs/BRIEF.md](docs/BRIEF.md) §7.
This file holds the planned slice order. Every milestone ends with a report and a stop for review.

## v0.1 — Trusted core

- [x] **M0 — Assessment and plan** (docs, ADRs; no feature code)
- [~] **M1 — Walking skeleton** (all slices built; macOS .app build/verification pending)
  1. Python project + `scripts/check.sh` / `pnpm check` (ruff, pyright, pytest, secret scanner) — green on empty suite.
  2. Runtime: stdin handshake, UDS server (0700 dir / 0600 socket), bearer secret (constant-time),
     peer-UID check, stdin-EOF watchdog. Security tests: no TCP/UDP listener, missing/wrong secret,
     secret absent from argv/env, exit on stdin close. (Linux-runnable; macOS re-run later.)
  3. Storage: SQLite WAL, migration runner, `settings` table + repository; restart-survival test.
  4. Structured JSON logging with central redaction; canary test.
  5. Tauri 2 app scaffold: React/TS/Vite/Tailwind, design-token file, seven screen shells with
     "Not available yet" states, strict CSP, capability file with only JARVIS commands.
  6. Rust bridge: spawn sidecar, secret generation, route allowlist, HTTP over UDS, event Channel,
     kill-on-exit. Rust tests + capability-file security test.
  7. Settings screen round-trip UI → Rust → backend; Vitest for the bridge client.
  8. Sidecar freezing (PyInstaller) + `.app` build on macOS; launch test; `lsof`/`ps` checks on macOS.
  9. Contract generation (JSON Schema → TS) with staleness check.
- [ ] **M2 — Trust kernel**: tool contract, executor + write-ahead intents + recovery, policy/grants,
      approval queue + native confirm, hash-chained audit, receipts, Security Center; single-step tasks.
- [ ] **M3 — Conversation and providers**: normalized model interface, 4 adapters, Keychain, routing/fallback,
      streaming chat + persistence + stop, Provider Settings and Command Center.
- [ ] **M4 — Memory**: history + memories, confirmation rules, FTS5 + vector retrieval, Memory Center.
- [ ] **M5 — Files + v0.1 release**: file tool via executor, Skills Center, Activity Center, release checklist.

## v0.2 — Tasks and terminal

- [ ] **M6 — Terminal** (allowlist + approval, no shell, sandbox, redaction)
- [ ] **M7 — Task engine + v0.2 release** (planner DAG, state machine, checkpoints/resume, budgets, Task History)

## v0.3 — Browser, screen and voice

- [ ] **M8 — Browser** (Playwright, dedicated profile, quarantine, injection flagging)
- [ ] **M9 — Desktop observation** (ScreenCaptureKit, exclusions, retention, cloud opt-in, audit)
- [ ] **M10 — Voice + v0.3 release** (STT/TTS adapters, push-to-talk, VAD, barge-in)

## Beyond v0.3 (design seams only, no code)

World model, proactive intelligence, public SDK/skills marketplace, devices/IoT, multi-device sync
on PostgreSQL, Windows and Linux builds.
