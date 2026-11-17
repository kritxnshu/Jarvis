# ADR-0004: Approval binding and native confirmation

**Status:** Accepted (2026-11-17)

## Context
Brief §4.11: approvals enforced in the backend, bound to exact parameters, single-use, expiring;
highest-risk approvals need a native macOS dialog so webview script can't approve alone.

## Decision
- **Digest:** SHA-256 of canonical JSON (sorted keys, UTF-8, no insignificant whitespace) of
  `{tool, tool_version, params, scope}`. Computed by the executor; never accepted from clients.
- **Lifecycle:** only the executor creates approval requests. The API offers approve/reject on an
  existing id. On execution the executor recomputes the digest; mismatch, expiry (default 10 min,
  configurable), or `used_at IS NOT NULL` → refuse + audit. Consumption is an atomic
  `UPDATE … WHERE used_at IS NULL` in the same transaction as the intent write.
- **Native confirmation** for categories purchase/financial, send_message, publish,
  permanent_delete, production_deploy: the webview may only call the Tauri command
  `confirm_high_risk_approval(id)`. Rust fetches the request summary from the backend, shows a
  native dialog from Rust (dialog plugin not granted to the webview), and on "Approve" sends
  `native_confirmation = HMAC-SHA256(launch_secret, "jarvis-native-confirm\0" || id || "\0" || digest)`.
  The generic bridge command rejects bodies containing that field. Backend refuses high-risk
  approvals lacking a valid token.

## Consequences
- A compromised webview can approve low/consequential actions through the normal UI path (it is
  the UI) but cannot approve highest-risk actions without the user clicking a native dialog.
- Test: request with valid secret and no approval → rejected and audited; parameter change →
  digest mismatch; replay → used; expired → refused; high-risk without token → refused.

## Implementation notes (M2, 2026-11-17)
- The executor recomputes the digest from the parameters it is about to run, so altering stored
  parameters after approval is refused (`approval_digest_mismatch`), not trusted.
- Refusals are audited in their own transaction after the failed one rolls back.
- The approval request text is redacted before storage (found by the canary acceptance test).
- Rust: `confirm_high_risk_approval` shows an `rfd` dialog on the main thread; the token is
  pinned across languages by `native_confirm::tests::token_matches_the_python_backend`.
- The native dialog itself cannot be clicked by automated tests; it is listed for manual
  verification in IMPLEMENTATION_STATUS.md.
