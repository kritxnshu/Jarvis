# ADR-0002: Local transport — UDS + stdin secret + peer UID

**Status:** Accepted (2026-11-17)

## Context
Brief §5.2: nothing but the JARVIS app may reach the backend; no TCP/UDP; secret over stdin.

## Decision
- HTTP/1.1 over a Unix domain socket at `<app_data>/run/<8 hex chars>/b.sock`; dir 0700,
  socket 0600 (umask 0o177 at bind, then `chmod` and verify). Served by uvicorn with `uds=`.
- Handshake: Rust writes one JSON line on stdin `{secret, socket_path, data_dir}`; sidecar replies
  `{"ready": true}` on stdout once bound. Stdin stays open; a watchdog thread exits on EOF
  (graceful shutdown, then hard `os._exit` after a deadline).
- Auth: `Authorization: Bearer <64 hex chars>`, compared with `hmac.compare_digest` in an ASGI
  middleware that runs before routing.
- Peer UID: checked per connection at accept time via a thin wrapper around uvicorn's protocol
  factory that reads `transport.get_extra_info("socket")` and calls `getpeereid`-equivalents
  (`LOCAL_PEERCRED` on macOS, `SO_PEERCRED` on Linux). Mismatch → close before parsing.
- Rust client: `hyper` over `tokio::net::UnixStream`; route allowlist; never exposes the secret.
- Interfaces: Python `Transport` (listen), Rust `BackendClient` trait — Windows named pipe later.

## Consequences
- Not reachable from browsers or the network; no CORS or DNS-rebinding surface.
- Relies on uvicorn internals for peer-cred hook; covered by a security test on both OSes so an
  upgrade that breaks it fails the check command.

## Implementation notes (M1, 2026-11-17)
- macOS limits socket paths to 104 bytes. `~/Library/Application Support/ai.jarvis.desktop/run/…`
  is long, so the launch directory is 8 random hex chars and the socket is `b.sock`; Rust refuses
  to launch if the path would exceed 103 bytes (`rundir::rejects_overlong_socket_paths`).
- Stale launch directories from crashed runs are removed at startup.
- The data directory is set to 0700 by the shell before launch.
- On shutdown the backend first closes open event streams, so graceful shutdown never stalls.
