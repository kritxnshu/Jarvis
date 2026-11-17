# ADR-0003: Freezing and launching the Python sidecar

**Status:** Accepted for Linux evidence; macOS .app build pending (2026-11-17)

## Context
Packaging Python inside a macOS .app is the biggest structural risk (brief §5.1). Needs: no
dependency on a system Python, code-signable, works on a fresh user account.

## Options
1. **PyInstaller `--onedir`** placed in `Contents/Resources/sidecar/`: mature, widely used with
   Tauri; every `.so`/`.dylib` must be signed; `--onefile` rejected (extracts to /tmp at each
   launch, slow, breaks signing and hardened runtime).
2. **python-build-standalone + venv copied into Resources**: no freezer magic, but more files to
   sign and more custom build scripting.
3. Nuitka: compiles to C; slower builds, heavier toolchain.

## Decision
Start with option 1 (PyInstaller onedir, arm64). The sidecar is launched by Rust from
`Resources` (ADR-0001). If M1 hits a blocker (signing, hardened runtime, dynamic imports of
FastAPI/uvicorn/pydantic-core), fall back to option 2 and record it here.

## Consequences
- Adds PyInstaller as a build-time dependency (justified in DEVELOPMENT.md when added).
- Without an Apple Developer ID only ad-hoc signing is possible: the .app runs locally but
  Gatekeeper will warn on other machines and notarization is impossible.
- Must be built on macOS (ADR-0010).

## Evidence so far (M1)
- `scripts/build_sidecar.sh` freezes the core with PyInstaller 6.22.3 `--onedir` (44 MB on Linux).
- `tests/desktop/test_frozen_sidecar.py` runs the frozen binary through the same handshake,
  auth, persistence and exit tests as the source tree — passing on Linux.
- `pnpm --filter @jarvis/desktop build:app:debug` bundles it as a Tauri resource; the built app
  launches `sidecar/jarvis-backend/jarvis-backend` and passes the desktop security tests (Linux).
- Not yet done: the same on macOS (arm64), plus code signing of every `.so`/`.dylib`. The CI macOS
  job builds the `.app`; nothing has been run on macOS yet.
