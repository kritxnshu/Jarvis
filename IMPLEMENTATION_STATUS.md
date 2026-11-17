# Implementation Status

Status vocabulary (BRIEF §3): Not started · In progress · Implemented · Tested · Verified ·
Tested — awaiting manual verification · Blocked.

_Last updated: 2026-11-17 (end of Milestone 0)._

## Capabilities

| #    | Capability                                   | Release              | Status      | Evidence (tests + command) | Last verified | Blockers |
|------|----------------------------------------------|----------------------|-------------|----------------------------|---------------|----------|
| 4.1  | Conversation — text                          | v0.1                 | Not started | —                          | —             | —        |
| 4.1  | Conversation — voice                         | v0.3                 | Not started | —                          | —             | —        |
| 4.2  | Persistent, editable personal memory         | v0.1                 | Not started | —                          | —             | —        |
| 4.3  | Model provider switching                     | v0.1                 | Not started | —                          | —             | Needs at least one API key or Ollama for live smoke tests (contract tests use fixtures) |
| 4.4  | Browser navigation and automation            | v0.3                 | Not started | —                          | —             | —        |
| 4.5  | Desktop observation with explicit permission | v0.3                 | Not started | —                          | —             | —        |
| 4.6  | Authorized file search and management        | v0.1                 | Not started | —                          | —             | —        |
| 4.7  | Controlled terminal execution                | v0.2                 | Not started | —                          | —             | —        |
| 4.8  | Multi-step task planning                     | v0.2                 | Not started | —                          | —             | —        |
| 4.9  | Background task persistence                  | v0.2                 | Not started | —                          | —             | —        |
| 4.10 | Execution verification and receipts          | v0.1 / v0.2 / v0.3   | Not started | —                          | —             | —        |
| 4.11 | Approval interface for consequential actions | v0.1                 | Not started | —                          | —             | —        |
| 4.12 | Complete task history and audit logs         | v0.1                 | Not started | —                          | —             | —        |

## Platform / infrastructure

| Item                                          | Milestone | Status      | Evidence | Blockers |
|-----------------------------------------------|-----------|-------------|----------|----------|
| Documentation skeleton, CLAUDE.md, ADRs       | M0        | Implemented | Files in repo (docs only; nothing to test) | — |
| Check command (`pnpm check`)                  | M1        | Not started | —        | —        |
| Tauri app launches sidecar                    | M1        | Not started | —        | —        |
| UDS transport + launch secret (5.2)           | M1        | Not started | —        | —        |
| Settings in SQLite with migrations            | M1        | Not started | —        | —        |
| Structured JSON logging with redaction        | M1        | Not started | —        | —        |
| Packaged macOS .app                           | M1        | Not started | —        | Needs macOS build host (ADR-0010) |

## Project facts (BRIEF §0)

The founder's brief left section 0 unfilled. Recorded as unknown; nothing has been guessed.

| Fact                                   | Value                    | Consequence until known |
|----------------------------------------|--------------------------|-------------------------|
| Repository                             | Empty (verified: no commits locally or on `origin`) | Fresh scaffold |
| Development machine                    | **Unknown** (macOS version, Apple Silicon/Intel) | Build targets `aarch64-apple-darwin` first; universal binary deferred |
| Model API keys                         | **Unknown**              | Providers show "Not configured"; live smoke tests skipped (opt-in) |
| Local models (Ollama)                  | **Unknown**              | Ollama adapter shows "Not configured / unreachable" |
| Voice provider accounts                | **Unknown**              | Irrelevant until v0.3 |
| Apple Developer ID                     | **Unknown**              | Unsigned / ad-hoc-signed builds only; Gatekeeper will warn; notarization not possible |
| Cloud session environment              | Linux x86_64 container (Python 3.13.18, uv 0.11.32, Node 22.23.4, pnpm 10.28.0, Rust 1.97.0) | macOS-only steps can't be run here (ADR-0010) |

## Current position

- **Release:** v0.1 — Trusted core
- **Milestone:** M0 — Assessment and plan — **complete, awaiting founder review.**
- **In progress:** nothing.

## Next step (after M0 approval)

M1, slice 1: scaffold the Python backend (`pyproject.toml` at repo root, `backend/src/jarvis/`),
the `scripts/check.sh` + `pnpm check` command with ruff, pyright, pytest and the in-repo secret
scanner, and a green empty test run. Then slice 2: UDS server with stdin secret handshake and its
security tests (Linux-runnable parts). Then the Tauri shell. See ROADMAP.md §M1 for the full slice order.
