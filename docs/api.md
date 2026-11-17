# Backend API

Served by `backend/src/jarvis/api/app.py` over the Unix socket. Requirements: BRIEF §5.2.

## Transport and auth (implemented)

- HTTP/1.1 over a Unix domain socket at `<app data>/run/<8 hex>/b.sock` (dir 0700, socket 0600).
  No TCP/UDP listener. Paths are kept ≤103 bytes for macOS `sun_path`.
- Every request: `Authorization: Bearer <64-hex launch secret>`, compared in constant time.
  Missing/invalid → `401 {"error":{"code":"unauthorized",...}}` before routing.
- Each connection's peer UID must equal the backend's UID, else it is closed before any parsing.
- No OpenAPI/docs routes. Validation errors never echo the request body.
- The Rust bridge forwards only allowlisted routes (`src-tauri/src/bridge/routes.rs`):
  `GET /v1/health`, `GET /v1/settings`, `PUT /v1/settings/{key}`. `/v1/events` is reachable only
  through the `subscribe_events` command.
- Every authenticated request is logged as `{method, path, status, ms}` — never bodies or headers.

## Routes (implemented)

| Method | Path | Response |
|---|---|---|
| GET | `/v1/health` | `HealthResponse {status, version, schema_version}` |
| GET | `/v1/settings` | `SettingsResponse {settings: Setting[]}` — every registered setting with its value or default |
| PUT | `/v1/settings/{key}` | body `SettingUpdate {value}` → `Setting`; `404 unknown_setting`, `422 invalid_setting_value` / `invalid_request` |
| GET | `/v1/events` | `application/x-ndjson` stream of `EventEnvelope {type, id, ts, task_id, schema_version, payload}` |

### Trust kernel (M2)

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/tasks` | `{tool, params, objective}` → `ExecutionView`. Runs one single-step task through the executor. **Not** on the bridge allowlist (the UI starts no tool runs yet). |
| GET | `/v1/tasks` | `TaskList` (newest first) |
| GET | `/v1/tasks/{id}` | `TaskDetail {task, receipt}` |
| POST | `/v1/tasks/{id}/review` | `{action_id, choice: happened\|retry\|cancel}` for Needs review; `happened` ⇒ user-attested, `retry` ⇒ new approval |
| GET | `/v1/approvals` | pending approvals (expired ones are swept first) |
| GET | `/v1/approvals/{id}` | one approval incl. digest and request text |
| POST | `/v1/approvals/{id}/decision` | `{approve, native_confirmation?}`; highest-risk needs the HMAC token only the Rust shell can compute; refusals are 403 and audited. The generic bridge refuses bodies containing `native_confirmation`. |
| POST | `/v1/audit/search` | `{type_prefix?, task_id?, text?, limit?, before_seq?}` → `AuditEntries` |
| GET | `/v1/audit/verify` | `{ok, entries, first_bad_seq, reason}` |
| GET | `/v1/audit/export/{json\|csv}` | `{format, content}` (complete, redacted). Reached by the UI only via the `save_audit_export` command |
| GET/POST | `/v1/grants` | list / add `{scope_type, scope_value, expires_at?}` |
| POST | `/v1/grants/{id}/revoke` | |

There is no route that creates an approval: only the executor does. Unauthenticated requests are
audited as `auth.rejected`.

Event types today: `chat.started`, `chat.delta`, `chat.finished`, `task.updated`, `system.stream_opened`, `system.heartbeat` (every 15 s idle), `settings.changed`.
The bridge adds `bridge.stream_closed` when the stream ends so the UI can resubscribe.

Registered settings (`config/settings_registry.py`) — only settings something honors:
`appearance.reduced_motion` (`system|on|off`), `appearance.show_status_bar` (bool).

TypeScript types for these payloads are generated into `packages/contracts/src/generated.ts`.

### Providers and conversation (M3)

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/providers` | `ProvidersResponse {providers, routes}`; keys appear only as `credential_hint` (••••abcd) |
| PUT | `/v1/providers/{id}` | `{base_url?, enabled?, key_optional? (OpenAI-compatible only)}` |
| PUT | `/v1/providers/{id}/credential` | `{secret}` → Keychain; 503 `keychain_unavailable` when no OS keychain. There is no route that reads a key back |
| POST | `/v1/providers/{id}/credential/delete` | |
| POST | `/v1/providers/{id}/check` | connectivity test → `{ok, detail, models, error_kind}` |
| PUT | `/v1/routes/{task}` | `{chain: [{provider_id, model}]}` ordered fallback; tasks: chat, planning, memory_extraction, vision, embeddings |
| GET/POST | `/v1/conversations` | list / create `{title}` |
| GET | `/v1/conversations/{id}/messages` | messages with `status` complete / streaming / interrupted / failed |
| POST | `/v1/conversations/{id}/messages` | `{text}` → `{user_message_id, message_id}`; the reply streams as `chat.started`, `chat.delta`, `chat.finished` events |
| POST | `/v1/messages/{id}/stop` | cancels the stream; partial text is saved as interrupted |

## Planned

`/v1/memory` (M4),
`/v1/files` (M5). There will be no route that creates an approval or confirms a memory from model output.
