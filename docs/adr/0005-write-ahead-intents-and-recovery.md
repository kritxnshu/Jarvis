# ADR-0005: Write-ahead intents and uncertain-action recovery

**Status:** Accepted (2026-11-17)

## Context
Brief §5.5: a timeout or crash is not evidence an action did or didn't happen.

## Decision
- Before any side-effecting `execute`, insert `action_intents` (action id, tool, digest,
  idempotency key = ULID, started_at) and commit with `synchronous=FULL`.
- Outcome rows are written after execution. Startup recovery scans intents without outcomes and
  marks those actions **Uncertain**; non-idempotent timeouts/connection losses also → Uncertain.
- Recovery by declared strategy: Idempotent → re-run with the same key (within retry limit);
  Reconcilable → run check, record evidence, then Completed(/Verified) or eligible for retry
  under normal approval; Manual or inconclusive → task **Needs review**.
- Needs review options: "It happened" → `UserAttested` (never Verified); "It didn't happen —
  retry" → new approval; "Cancel task".
- Local ops avoid uncertainty: atomic write (tmp + fsync + rename + dir fsync); cross-volume move =
  copy → hash verify → delete source; multi-file ops journaled.

## Consequences
- Every side-effect tool must declare a recovery strategy; the registry refuses tools without one.
- Crash tests use a subprocess backend killed with SIGKILL at injected points plus a local fixture
  server that counts effects.
