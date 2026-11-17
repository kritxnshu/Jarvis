# Database

Code: `backend/src/jarvis/storage/`. File: `<app data>/jarvis.sqlite3` (mode 0600).

## Engine and conventions (ADR-0007)

- SQLite, WAL mode, `foreign_keys=ON`, `synchronous=FULL` (intents and audit must survive power loss).
- Access only through repository classes in `jarvis.storage`; no SQL outside `storage/`.
- Migrations: `backend/src/jarvis/storage/migrations/NNNN_name.sql`, applied in order inside a
  transaction, tracked in `schema_migrations(version, name, applied_at, checksum)`. Applied
  migrations are never edited; the runner refuses on checksum mismatch.
- IDs: ULIDs as TEXT. Timestamps: UTC ISO-8601 TEXT with milliseconds.
- No secrets in any table (enforced by the canary test).

## Implemented

| Table | Migration | Columns |
|---|---|---|
| `schema_migrations` | runner | `version INTEGER PK, name TEXT, checksum TEXT (sha256 of the .sql), applied_at TEXT` |
| `settings` | 0001_settings | `key TEXT PK, value_json TEXT, updated_at TEXT` — only keys in the settings registry are accepted |

Migrations run inside one transaction each (script + bookkeeping row), so a failing migration
leaves no partial schema (`tests/unit/test_migrator.py`).

## Planned

| Table | Milestone | Purpose |
|---|---|---|
| `tasks` | M2 | objective, state (BRIEF §4.9 states), reason, timestamps |
| `actions` | M2 | task_id, tool, digest, idempotency_key, state, recovery strategy |
| `action_intents` | M2 | write-ahead intent: action_id, digest, idempotency key, started_at |
| `action_outcomes` | M2 | action_id, outcome JSON, completed_at, verification evidence |
| `approvals` | M2 | action digest, category, request text, expires_at, decided_at, decision, used_at, native_confirmed |
| `permission_grants` | M2 | scope type (dir/domain/command class), scope value, expires_at |
| `audit_log` | M2 | seq, ts, type, actor, payload (redacted), prev_hash, hash |
| `receipts` | M2 | task_id, JSON receipt |
| `conversations`, `messages` | M3 | history; messages have status (complete/interrupted), provider, model |
| `providers`, `routes` | M3 | provider config (no keys; Keychain ref only), per-task routing, fallback order |
| `memories`, `memory_events` | M4 | text, type, origin, status, source_ref, confirmed_by/at, supersedes |
| `memories_fts` | M4 | FTS5 index over memory and history text |
| `memory_vectors` | M4 | vector index (sqlite-vec) behind `VectorIndex` |
| `file_ops_journal`, `trash_items` | M5 | crash-safe multi-file ops; restorable trash |
| `checkpoints`, `task_steps` | M7 | multi-step tasks |
