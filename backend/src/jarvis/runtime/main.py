"""Sidecar entry point: handshake on stdin, bind the socket, serve, exit when stdin closes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import uvicorn

from jarvis import __version__
from jarvis.api.app import AppDeps, create_app
from jarvis.runtime.handshake import HandshakeError, LaunchConfig, read_launch_config
from jarvis.runtime.logging_setup import configure_logging
from jarvis.runtime.protocol import make_peer_checked_protocol
from jarvis.runtime.uds import SocketSetupError, bind_unix_socket
from jarvis.runtime.watchdog import start_stdin_watchdog
from jarvis.services import build_services
from jarvis.storage.db import Database
from jarvis.storage.migrator import apply_migrations
from jarvis.tools.registry import ToolRegistry, build_production_registry
from jarvis.trust.redaction import Redactor
from jarvis.trust.secrets import SecretStore

log = logging.getLogger("jarvis.runtime")

EXIT_HANDSHAKE = 2
EXIT_SETUP = 3


def _prepare_data_dir(data_dir: Path) -> None:
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if data_dir.stat().st_uid != os.getuid():
        raise SocketSetupError("data directory is not owned by the current user")


def _announce(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


async def _serve(server: uvicorn.Server, sock_list: list[object]) -> None:
    task = asyncio.create_task(server.serve(sockets=sock_list))  # type: ignore[arg-type]
    # uvicorn exposes no startup callback; poll its flag briefly.
    while not server.started and not task.done():  # noqa: ASYNC110
        await asyncio.sleep(0.01)
    if server.started:
        _announce({"ready": True, "pid": os.getpid(), "version": __version__})
        log.info("backend ready")
    await task


def run(
    config: LaunchConfig,
    registry: ToolRegistry | None = None,
    secrets: SecretStore | None = None,
) -> int:
    redactor = Redactor()
    redactor.register(config.secret)
    _prepare_data_dir(config.data_dir)
    configure_logging(config.data_dir / "logs", redactor)

    db = Database(config.data_dir / "jarvis.sqlite3")
    try:
        applied = apply_migrations(db)
        log.info("database ready", extra={"migrations_applied": applied})
        services = build_services(
            db, redactor, config.secret, registry or build_production_registry(), secrets=secrets
        )
        bus = services.bus
        app = create_app(AppDeps(secret=config.secret, services=services))
        sock = bind_unix_socket(config.socket_path)
        uv_config = uvicorn.Config(
            app,
            http=make_peer_checked_protocol(os.getuid()),
            ws="none",
            lifespan="on",
            log_config=None,
            access_log=False,
            timeout_graceful_shutdown=2,
            server_header=False,
        )
        server = uvicorn.Server(uv_config)

        def request_shutdown() -> None:
            # End open event streams first so graceful shutdown doesn't wait them out.
            bus.close_all_threadsafe()
            server.should_exit = True

        start_stdin_watchdog(sys.stdin.buffer, request_shutdown)
        try:
            asyncio.run(_serve(server, [sock]))
        finally:
            sock.close()
            config.socket_path.unlink(missing_ok=True)
    finally:
        db.close()
    log.info("backend stopped")
    return 0


def main(registry: ToolRegistry | None = None, secrets: SecretStore | None = None) -> int:
    """Entry point. Parameters exist for the test harness; production passes nothing and gets
    the production tool registry and the macOS Keychain."""
    try:
        config = read_launch_config(sys.stdin.buffer)
    except HandshakeError as exc:
        sys.stderr.write(f"jarvis: handshake failed: {exc}\n")
        return EXIT_HANDSHAKE
    try:
        return run(config, registry, secrets)
    except SocketSetupError as exc:
        log.error("startup failed", extra={"error": str(exc)})
        sys.stderr.write(f"jarvis: startup failed: {exc}\n")
        return EXIT_SETUP
