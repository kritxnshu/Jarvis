# ADR-0009: Contract generation from Pydantic

**Status:** Accepted (2026-11-17)

## Decision
- Pydantic models in `jarvis.api.schemas` are the source of truth. A script dumps a combined JSON
  Schema and runs `json-schema-to-typescript` to write `packages/contracts/src/generated.ts`.
- The check command regenerates into a temp dir and fails if output differs from the committed file.
- Rust reads only a few fields (event envelope, approval summary) through hand-written serde
  structs, validated by a Rust test against the exported JSON Schema samples.

## Consequences
- One dev dependency (`json-schema-to-typescript`). Avoids full Rust codegen (typify) until the
  bridge needs more than opaque forwarding.
