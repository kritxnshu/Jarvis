# Security

> **Status: design only (M0).** No security control below exists in code yet. Each control
> gets a link to its tests when implemented. Requirements: [docs/BRIEF.md](docs/BRIEF.md) §5.2, §5.4, §8.

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

## 5. Reporting

Single-founder project; report issues privately to the repository owner.
