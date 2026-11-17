# Security

Requirements: [docs/BRIEF.md](docs/BRIEF.md) §5.2, §5.4, §8. Section 5 lists which controls exist
and the tests that cover them; everything else here is design for later milestones.

## 1. Assets

- The user's files in granted directories, and the ability to change them.
- Model-provider API keys and other credentials (Keychain).
- Conversation history, memories, audit log, screen frames.
- The ability to take actions on the user's behalf (shell, browser, messages).

## 2. Trust boundaries

| Boundary | Trusted side | Untrusted side | Control |
|---|---|---|---|
| WebView ↔ Rust | Rust | WebView (could run injected script) | Command allowlist via Tauri capabilities; strict CSP; no secret in webview; native confirm for highest-risk approvals |
| Rust ↔ Python | both (same app) | other local processes | UDS in 0700 dir, socket 0600; per-launch secret over stdin; peer-UID check; no TCP/UDP |
| Python ↔ model providers | Python | provider responses | Responses are data; tool calls are proposals that go through policy + approval |
| Python ↔ tool outputs / web / files / screenshots | Python | content | Marked untrusted in model context; can't grant permissions, approve, or confirm memory; embedded instructions are surfaced to the user |
| Executor ↔ OS | policy engine | everything else | Scoped, expiring grants; approvals bound to action digests; terminal allowlist + sandbox |

## 3. Threat model

**Protects against:**
- Web pages (including pages the JARVIS browser visits): no listening port to reach, no DNS
  rebinding surface, page content cannot grant or approve anything.
- The network: nothing listens on TCP/UDP.
- Other user accounts on the Mac: directory/socket permissions plus peer-UID check.
- Local processes running as the same user that don't hold the launch secret: requests without
  the secret are rejected; the secret is not in argv or env (not visible via `ps`).
- A compromised webview script: it can't call commands outside its allowlist, can't reach the
  backend directly, and can't produce the native confirmation required for highest-risk actions.
- Prompt injection and memory poisoning via untrusted content (see §2 last rows, BRIEF §4.2 rule 3).

**Does not protect against:**
- Malware already running as the same user with debugging-level access (e.g. able to attach
  to the JARVIS processes, read their memory, or inject into them). Such malware can read the
  secret and act as JARVIS. This is a deliberate, stated limit.
- A malicious root/admin user.
- What a cloud model provider does with data after JARVIS sends it.

**Audit log integrity:** entries are hash-chained. On a single-user machine this is **tamper
evidence, not tamper prevention**: someone with write access to the database can rewrite the
whole chain consistently. Verification detects edits to individual entries and breaks in the chain.

## 4. Known risks in the plan (tracked)

| Risk | Mitigation / status |
|---|---|
| Python sidecar packaging, signing and notarization inside .app | Prove in M1 (ADR-0003). Without an Apple Developer ID, only ad-hoc signing is possible. |
| `sandbox-exec` is deprecated by Apple | Use while it works; if unreliable, mark terminal isolation test **Blocked** here rather than claim isolation (M6). |
| Keychain item ACLs tie to the signing identity of the creating binary | Unsigned/ad-hoc dev builds may prompt or lose access after rebuilds; documented in ADR-0008. |
| Peer-credential checks need raw-socket access under uvicorn | Custom accept wrapper (ARCHITECTURE §2); tested on Linux (`SO_PEERCRED`) and macOS (`LOCAL_PEERCRED`). |
| Tauri capability misconfiguration exposing generic plugins | Security test parses capability files and fails on any non-JARVIS permission. |
| Secret leakage into logs/DB/exports | Central redaction before every write; canary `sk-test-JARVIS-CANARY` scanned for in DB, logs, exports and `ps` output. |
| Supply chain (PyPI/npm/crates) | Lockfiles committed (uv.lock, pnpm-lock.yaml, Cargo.lock); minimal dependency list with justifications in DEVELOPMENT.md. |
| macOS-only controls can't be verified from Linux cloud sessions | ADR-0010: such items stay "Tested" or "awaiting manual verification" until run on macOS. |

## 5. Implemented controls (M1) and their tests

All tests below pass on Linux (`pnpm check`). None has been run on macOS yet (ADR-0010).

| Control | Code | Tests |
|---|---|---|
| No TCP/UDP listener (backend, app) | `runtime/uds.py`, `runtime/main.py` | `tests/security/test_backend_reachability.py::test_backend_opens_no_tcp_or_udp_socket`, `tests/desktop/test_desktop_app.py::test_no_tcp_or_udp_listeners_on_app_or_backend` |
| 0700 run dir / 0600 socket / 0700 data dir; refuses shared or symlinked dirs | `runtime/uds.py`, `src-tauri/src/rundir.rs` | `tests/unit/test_uds.py`, `rundir::tests::*`, `test_running_socket_is_private`, `test_refuses_to_start_with_shared_socket_directory`, `test_app_starts_backend_on_private_socket` |
| Launch secret: 256-bit CSPRNG, stdin only, constant-time check | `src-tauri/src/secret.rs`, `sidecar.rs`, `api/auth.py` | `test_requests_without_valid_secret_are_rejected` (missing/wrong/scheme/empty), `test_secret_in_query_string_is_not_accepted`, `bridge_e2e::wrong_secret_is_rejected`, `test_backend_rejects_requests_without_the_apps_secret` |
| Secret not in argv/env of either process | `sidecar.rs` (`env_clear`, fixed PATH) | `test_secret_not_in_process_arguments_or_environment`, `bridge_e2e::secret_is_not_in_backend_argv_or_environment`, `test_desktop_app.py::test_no_secret_in_process_listings` |
| Peer-UID check per connection | `runtime/peercred.py`, `runtime/protocol.py` | `test_connection_from_unexpected_uid_is_dropped` (Linux `SO_PEERCRED`; macOS `LOCAL_PEERCRED` path untested) |
| Backend exits when the app dies | `runtime/watchdog.py` | `test_backend_exits_when_stdin_closes`, `test_backend_exits_when_parent_is_killed`, `test_killing_the_app_stops_the_backend` (real app, SIGKILL) |
| Bridge forwards only allowlisted routes | `src-tauri/src/bridge/routes.rs` | `routes::tests::allowed_routes`, `routes::tests::refused_routes` |
| Webview: strict CSP, 3 commands only, no generic plugins | `tauri.conf.json`, `capabilities/main.json`, `build.rs` | `tests/security/test_webview_config.py` (static). Runtime check inside WKWebView: **awaiting manual verification on macOS** |
| Redaction before logs; secrets never on disk | `trust/redaction.py`, `runtime/logging_setup.py` | `tests/unit/test_redaction.py`, `test_launch_secret_and_canary_never_written_to_disk` |
| Repository secret scan | `scripts/secret_scan.py` | `tests/unit/test_secret_scan.py`; runs in `pnpm check` |

### Added in M2 (trust kernel)

| Control | Code | Tests |
|---|---|---|
| Approvals bound to SHA-256 action digest, recomputed from the parameters about to run; single-use; 10-minute expiry | `trust/approvals.py`, `execution/executor.py` | `tests/acceptance/test_4_11_approvals.py` (parameter change, replay, expiry) |
| Highest-risk categories need an HMAC token computed by Rust after a native dialog; the generic bridge strips nothing and refuses bodies carrying a token | `trust/approvals.py`, `src-tauri/src/native_confirm.rs`, `routes.rs` | `test_compromised_ui_cannot_approve_highest_risk_without_native_confirmation`, `native_confirm::tests::*`, `routes::tests::native_confirmation_never_passes_the_generic_bridge`. Dialog itself: **awaiting manual verification** |
| No code path lets a request create an approval | `api/trust_routes.py` (list/get/decide only) | `test_no_route_creates_or_grants_an_approval_from_model_output` |
| Write-ahead intents; unknown outcomes are Uncertain, never Failed or Completed; no blind re-runs | `execution/executor.py`, `execution/recovery.py` | `tests/acceptance/test_4_10_receipts_recovery.py` (SIGKILL + restart) |
| Hash-chained append-only audit log; guard triggers; redaction before write | `trust/audit.py`, migration 0002 | `tests/unit/test_audit.py`, `tests/acceptance/test_4_12_audit.py` |
| Directory grants resolve symlinks and `..` before comparison | `trust/policy.py` | `tests/unit/test_policy.py` |
| Test-only tools never in production | `tools/registry.py::build_production_registry`, fixtures under `tests/` | `test_production_registry_contains_no_test_tools` |

### Added in M3 (providers and conversation)

| Control | Code | Tests |
|---|---|---|
| API keys only in the Keychain; DB stores a masked hint; no route reads a key back; keys registered with the redactor on save and at startup | `trust/secrets.py`, `providers/registry.py`, bridge allowlist | `test_saved_key_is_masked_and_never_stored_or_exported`, `test_without_an_os_keychain_keys_are_refused_not_stored_elsewhere`, `test_keys_go_to_the_macos_keychain` (macOS), `routes::tests::conversation_and_provider_routes` |
| Keys travel only in headers, never URLs | `providers/adapters/*` | `test_streams_text_deltas_usage_and_done` (all adapters) |
| Fallback never switches providers after output has started | `core/routing.py` | `test_fallback_on_provider_failure_is_used_and_audited` |
| Retention policy shown as text; the webview never navigates to provider sites | `ProviderSettings.tsx`, CSP | `ChatScreens.test.tsx`, `test_webview_config.py` |

## 6. Reporting

Single-founder project; report issues privately to the repository owner.
