# Backend API

> **Status (M0): no routes exist.** This page documents the conventions routes will follow and
> the planned M1 routes. It is updated as each route is implemented.

## Transport and auth

- HTTP/1.1 over a Unix domain socket (path known only to the Rust shell). No TCP/UDP.
- Every request: `Authorization: Bearer <launch-secret>`. Missing/wrong → `401`, audited (from M2).
- Peer UID must equal the backend's UID; otherwise the connection is closed before any HTTP parsing.
- All routes are versioned under `/v1/`. The Rust bridge forwards only routes in its allowlist
  (`apps/desktop/src-tauri/src/bridge/routes.rs`, planned).

## Conventions

- JSON bodies validated by Pydantic v2; schemas exported to `packages/contracts/`.
- Errors: `{"error": {"code": "snake_case", "message": "human readable", "details": {...}}}`.
- Streaming: `application/x-ndjson`, one event envelope per line:
  `{"type", "id", "ts", "task_id", "schema_version", "payload"}`.
- Every route has a timeout; no route blocks indefinitely except `GET /v1/events`.

## Planned M1 routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | liveness + version + schema version |
| GET | `/v1/settings` | list settings |
| PUT | `/v1/settings/{key}` | set a setting (validated against a settings registry) |
| GET | `/v1/events` | NDJSON event stream |

Later milestones add `/v1/approvals`, `/v1/audit`, `/v1/tasks`, `/v1/chat`, `/v1/providers`,
`/v1/memory`, `/v1/files`. There will be **no** route that creates an approval or confirms a
memory on behalf of model output.
