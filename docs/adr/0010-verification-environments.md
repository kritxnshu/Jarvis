# ADR-0010: Where things can be tested vs verified

**Status:** Accepted (2026-11-17)

## Context
Cloud development sessions run in a Linux x86_64 container. The brief defines **Verified** as
acceptance tests passing end to end on macOS. Several items are macOS-only: building/signing the
.app, Keychain, `LOCAL_PEERCRED`, `sandbox-exec`, ScreenCaptureKit, TCC permission prompts,
native dialogs, `lsof` checks against the real app.

## Decision
- Python core and most security tests are written to run on both Linux and macOS (OS-specific
  pieces behind interfaces with fakes). On Linux they can reach **Tested**.
- macOS-only tests are marked `@pytest.mark.macos` and print `SKIPPED (requires macOS)` on Linux —
  never a silent pass. Capabilities stay at **Tested** / **Tested — awaiting manual verification**
  until run on macOS.
- Paths to **Verified**, in order of preference (founder to choose):
  1. A GitHub Actions `macos-14`/`macos-15` (arm64) workflow that runs `pnpm check` and builds the
     .app (unsigned/ad-hoc). Consumes the founder's Actions minutes.
  2. Attaching the founder's Mac to a session (Remote Control) so commands run there.
  3. Written manual steps the founder runs locally and reports back.
  Items needing human interaction (TCC prompts, microphone) always use option 3.

## Consequences
- The status file will clearly separate Linux-tested from macOS-verified evidence.
