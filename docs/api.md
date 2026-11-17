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

Event types today: `system.stream_opened`, `system.heartbeat` (every 15 s idle), `settings.changed`.
The bridge adds `bridge.stream_closed` when the stream ends so the UI can resubscribe.

Registered settings (`config/settings_registry.py`) — only settings something honors:
`appearance.reduced_motion` (`system|on|off`), `appearance.show_status_bar` (bool).

TypeScript types for these payloads are generated into `packages/contracts/src/generated.ts`.

## Planned

`/v1/approvals`, `/v1/audit`, `/v1/tasks` (M2), `/v1/chat`, `/v1/providers` (M3), `/v1/memory` (M4),
`/v1/files` (M5). There will be no route that creates an approval or confirms a memory from model output.
