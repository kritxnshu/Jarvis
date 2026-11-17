# Architecture

> **Status (M1):** sections 1–3, 7 (settings only) and 8 are implemented; sections 4–6 and the rest
> of 7 are design for M2+. Decisions: [docs/adr/](docs/adr/). Requirements: [docs/BRIEF.md](docs/BRIEF.md) §5.

## 1. Process model

```
┌──────────────────────── JARVIS.app ────────────────────────────────────────┐
│                                                                            │
│  WebView (React + TS)            Rust shell (Tauri 2)        Python core   │
│  ─────────────────────           ────────────────────        ───────────   │
│  screens, design tokens  invoke  command allowlist   HTTP/1.1  FastAPI     │
│  no secret, strict CSP  ───────► route allowlist  ──over UDS──► routes     │
│                          Channel  native dialogs    + secret   executor    │
│                         ◄─────── event forwarder ◄── NDJSON ── event bus   │
│                                  sidecar lifecycle  stdin pipe  watchdog   │
│                                  macOS services                  SQLite    │
└────────────────────────────────────────────────────────────────────────────┘
```

- **WebView** talks only to Rust via Tauri commands and Channels. It never sees the backend
  socket path or secret.
- **Rust shell** owns the window, tray/menu bar, native OS integrations (behind a `platform`
  trait so Windows/Linux can be added), native confirmation dialogs, and the sidecar lifecycle.
  It forwards only allowlisted backend routes. It is deliberately thin: no business logic.
- **Python core** owns orchestration, providers, memory, tasks, tools, policy, audit.

See ADR-0001 (stack/process model), ADR-0002 (transport and auth), ADR-0003 (sidecar packaging).

## 2. Launch and transport (BRIEF §5.2)

1. Rust creates `<app_data>/run/<8 hex>/` with mode 0700 (socket `b.sock`, path ≤103 bytes) and generates a 256-bit secret
   from the OS CSPRNG.
2. Rust spawns the sidecar with an **empty-but-minimal environment** and no secret in argv/env,
   then writes one JSON line to its stdin: `{"secret": "<hex>", "socket_path": "...", "data_dir": "..."}`.
   Stdin stays open.
3. The sidecar binds a Unix domain socket at `socket_path` (umask so it's 0600), then prints
   `{"ready": true}` on stdout. It never opens TCP/UDP.
4. A watchdog thread blocks on stdin; EOF (Tauri died) → graceful shutdown with a hard
   deadline → process exit.
5. Every request carries `Authorization: Bearer <secret>`; the backend compares with
   `hmac.compare_digest`. On accept, the backend checks peer credentials (`LOCAL_PEERCRED`/
   `getpeereid` on macOS, `SO_PEERCRED` on Linux) and rejects any UID other than its own.
   Peer-credential checking happens at connection accept in a custom asyncio server wrapper
   around uvicorn's protocol, because ASGI does not expose the raw socket.
6. Streaming (chat deltas, task events) uses a long-lived NDJSON response from `GET /v1/events`
   that Rust relays onto a Tauri Channel.

The transport is behind a `Transport` interface on both sides (Rust: `BackendClient` trait;
Python: `listen(config) -> Server`) so Windows can use a named pipe with an ACL later.

## 3. Repository layout

```
/
├─ apps/desktop/                 Tauri app
│  ├─ src/                       React + TS UI (screens/, components/, design/tokens.ts, bridge/)
│  └─ src-tauri/                 Rust: main.rs, bridge/, sidecar/, platform/, approvals/
├─ backend/src/jarvis/           Python core
│  ├─ api/                       FastAPI routes on the socket; auth middleware
│  ├─ core/                      intent, context assembly, routing, planning, responses
│  ├─ memory/                    history, memories, retrieval
│  ├─ tools/                     tool implementations + registry
│  ├─ execution/                 executor, intents, recovery, task state machine, receipts
│  ├─ trust/                     policy, permissions, approvals, secrets, audit, redaction
│  ├─ providers/                 model + voice adapters, registry
│  ├─ perception/                text, voice, screen, app context (v0.3 mostly)
│  ├─ storage/                   SQLite connection, repositories, migrations/
│  ├─ platform/                  OS-service interfaces (keychain, sandbox, fs metadata)
│  └─ runtime/                   startup, config, logging, stdin handshake, watchdog
├─ packages/contracts/           generated TS types from backend JSON Schema
├─ tests/
│  ├─ unit/  integration/  security/
│  ├─ acceptance/                one file per capability (test_4_06_files.py, …)
│  └─ fixtures/                  fixture sites, recorded provider responses, test-only tools
├─ scripts/check.sh              the check command
├─ docs/                         BRIEF, api, database, adr/
└─ pyproject.toml, package.json, pnpm-workspace.yaml, Cargo workspace in src-tauri
```

Test-only tools live under `tests/fixtures/` and are registered only by test conftest code,
never by `jarvis.tools.registry` itself; a security test asserts the production registry
contains none of them.

## 4. Python module boundaries (BRIEF §5.3)

Dependency direction (lower may not import higher):

```
api  →  core  →  execution  →  tools  →  trust  →  storage
         ↓          ↓            ↓
       memory    providers    platform
```

- `trust/` and `storage/` import nothing above them. `trust/` is the only place that can
  create approvals or confirm memories, and only from `api/` routes reached by user actions.
- `providers/` adapters are the only code that knows vendor wire formats (ADR-0006).
- An import-linter-style test (plain pytest walking `ast` imports) enforces the direction.

## 5. Tool contract and executor (BRIEF §5.4–5.5)

```python
class Tool(Protocol[In, Out]):
    name: str
    input_model: type[In]; output_model: type[Out]
    risk: Risk                       # read_only | low | consequential | highest
    category: ApprovalCategory | None
    permissions: list[PermissionRequirement]
    idempotent: bool
    timeout_s: float
    recovery: Recovery | None        # Idempotent | Reconcilable(check) | Manual  (side-effect tools)
    async def execute(self, inp: In, ctx: ExecCtx) -> Out: ...
    async def verify(self, inp: In, out: Out, ctx: ExecCtx) -> Verification: ...
```

Executor pipeline: validate → policy check → approval (if required, bound to action digest)
→ **write-ahead intent** (fsync'd SQLite txn) → execute with timeout → record outcome →
verify → receipt + audit entry. Action states: Planned → Attempted → Completed → Verified, plus
Failed, Uncertain, Unverifiable, UserAttested. Startup runs recovery over intents with no
outcome (ADR-0005).

The action digest is SHA-256 over canonical JSON (sorted keys, no whitespace) of
`{tool, version, params, scope}`. Approvals bind to it (ADR-0004).

## 6. Approvals and native confirmation (BRIEF §4.11)

- Approval requests are created only by the executor. API routes can approve/reject an
  existing request id; there is no route or tool that creates an approval from model output.
- Each approval: id, digest, category, expiry, `used_at`. Granting is single-use and checked
  inside the executor transaction that consumes it.
- Highest-risk categories need a native confirmation: the webview calls a dedicated Tauri
  command; Rust shows a native dialog (from Rust only; the dialog plugin is not exposed to the
  webview) and, only if the user confirms, sends
  `native_confirmation = HMAC-SHA256(secret, "native-confirm\0" + approval_id + "\0" + digest)`.
  The webview cannot compute it (it doesn't have the secret), and the generic forwarding
  command strips/never sets that field. See ADR-0004.

## 7. Data (BRIEF §5.6)

SQLite (WAL, `synchronous=FULL` for intents/audit) behind repository classes; numbered SQL
migrations applied by a small in-house runner (ADR-0007). FTS5 for keyword retrieval; vector
search behind a `VectorIndex` interface (sqlite-vec planned for M4). Artifacts (trash, backups,
quarantine, frames) in the app data dir. Secrets in Keychain via a `SecretStore` interface
(ADR-0008). Schema: [docs/database.md](docs/database.md).

## 8. Contracts and events (BRIEF §5.7)

Pydantic models are the single source of truth. `scripts/gen-contracts` exports JSON Schema
and generates TS types into `packages/contracts/` (ADR-0009); the check command fails if the
generated output is stale. The Rust bridge treats bodies as opaque JSON except for the few
fields it must read (event envelope `type`, approval ids), which get hand-written serde
structs checked by a contract test against the same schema.

Event envelope: `{type, id, ts, task_id, schema_version, payload}`.

## 9. Seams for later (BRIEF §11) — no code

Tool registry (skills/SDK), permission contracts, storage repositories (PostgreSQL), `VectorIndex`
(pgvector), `Transport` (named pipes), `platform` traits (Windows/Linux), provider registry.
