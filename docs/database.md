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
| `tasks` | 0002_trust_kernel | `id, objective (redacted), state (BRIEF §4.9 states), state_reason, created_at, updated_at` |
| `actions` | 0002 | `id, task_id, tool, tool_version, params_json (redacted), digest, idempotency_key, risk, category, recovery, state, attempts, approval_id, output_json, error, verification_json, timestamps` |
| `action_intents` | 0002 | write-ahead intent committed before execution: `id, action_id, attempt, digest, idempotency_key, started_at` |
| `action_outcomes` | 0002 | `intent_id PK, action_id, outcome (completed/failed/uncertain), detail_json, finished_at`; an intent without an outcome after restart ⇒ Uncertain |
| `approvals` | 0002 | `id, action_id, digest, category, highest_risk, request_json (redacted), status (pending/approved/rejected/expired/used), created_at, expires_at, decided_at, native_confirmed, used_at` |
| `permission_grants` | 0002 | `id, scope_type (directory/domain/command_class/tool), scope_value (directories stored realpath'd), created_at, expires_at, revoked_at` |
| `audit_log` | 0002 | `seq PK, ts, type, actor, task_id, payload_json (redacted), prev_hash, hash`; triggers refuse UPDATE/DELETE; hash = SHA-256(prev_hash ‖ canonical entry) |
| `providers` | 0003_conversation_providers | `id, kind, display_name, base_url, key_optional, enabled, has_credential, credential_hint (masked), retention_policy_url` — the key itself is only in the Keychain |
| `model_routes` | 0003 | `task PK (chat/planning/memory_extraction/vision/embeddings), chain_json [{provider_id, model}], updated_at` |
| `conversations` | 0003 | `id, title, created_at, updated_at` |
| `messages` | 0003 | `id, conversation_id, role, content (redacted), status (complete/streaming/interrupted/failed), provider_id, model, error, input_tokens, output_tokens, timestamps` |
| `receipts` | 0002 | `task_id PK, receipt_json, updated_at` — rebuilt from recorded rows on every task change |

Migrations run inside one transaction each (script + bookkeeping row), so a failing migration
leaves no partial schema (`tests/unit/test_migrator.py`).

## Planned

| Table | Milestone | Purpose |
|---|---|---|
| `memories`, `memory_events` | M4 | text, type, origin, status, source_ref, confirmed_by/at, supersedes |
| `memories_fts` | M4 | FTS5 index over memory and history text |
| `memory_vectors` | M4 | vector index (sqlite-vec) behind `VectorIndex` |
| `file_ops_journal`, `trash_items` | M5 | crash-safe multi-file ops; restorable trash |
| `checkpoints`, `task_steps` | M7 | multi-step tasks |
