# ADR-0003: Freezing and launching the Python sidecar

**Status:** Proposed — must be proven by a working .app in M1 (2026-11-17)

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
