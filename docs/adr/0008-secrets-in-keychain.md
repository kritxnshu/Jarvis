# ADR-0008: Secrets in the Keychain behind SecretStore

**Status:** Accepted (2026-11-17)

## Decision
- `SecretStore` interface (`put`, `get`, `delete`, `exists`, `masked`). macOS implementation via
  the `keyring` package (Keychain backend), service name `ai.jarvis.app`. Tests use an in-memory
  fake; a macOS-only integration test exercises the real Keychain.
- Keys enter via UI → Rust → backend `PUT`; responses only ever contain a masked form
  (e.g. `sk-…ABCD`). DB rows store only a reference name.
- Secrets are never placed in child-process environments; the redactor knows every stored secret
  value at runtime (exact-match redaction) in addition to pattern-based redaction.

## Consequences
- Keychain ACLs are tied to the creating binary's code signature; ad-hoc/unsigned dev builds may
  show access prompts or lose access after a rebuild. Documented for the founder; resolved by a
  stable signing identity (Developer ID, unknown).
