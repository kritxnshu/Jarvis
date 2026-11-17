# ADR-0007: Storage — SQLite, in-house migrations, FTS5, vector interface

**Status:** Accepted (2026-11-17)

## Decision
- stdlib `sqlite3` (no ORM), WAL, repositories in `jarvis.storage`. SQL stays portable enough
  for a later PostgreSQL implementation of the same repository interfaces.
- Migrations: numbered `.sql` files + ~100-line runner with checksums (no Alembic: no ORM to
  autogenerate from, and one fewer dependency).
- Keyword search: FTS5 (bundled with Python's SQLite on macOS; checked at startup with a clear
  error if missing). Vector search: `VectorIndex` interface; `sqlite-vec` implementation in M4.
- Deletion must remove rows from base table, FTS index and vector index in one transaction.
- Long-running DB work runs in a thread executor so the event loop never blocks.

## Consequences
- Hand-written SQL needs tests per repository; schema documented in docs/database.md.
