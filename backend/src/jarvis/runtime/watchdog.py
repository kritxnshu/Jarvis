"""Exit when stdin closes: the Rust shell holds the other end, so EOF means it died."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import BinaryIO

log = logging.getLogger("jarvis.runtime.watchdog")


def start_stdin_watchdog(
    stream: BinaryIO,
    request_shutdown: Callable[[], None],
    hard_deadline_s: float = 3.0,
    hard_exit: Callable[[int], None] = os._exit,
) -> threading.Thread:
    def run() -> None:
        try:
            while stream.read(4096):
                pass  # The shell sends nothing after the handshake; discard anything else.
        except (OSError, ValueError):
            pass  # A broken or closed stdin means the same thing as EOF.
        log.info("stdin closed; shutting down")
        request_shutdown()
        time.sleep(hard_deadline_s)
        log.error("graceful shutdown exceeded deadline; forcing exit")
        hard_exit(0)

    thread = threading.Thread(target=run, name="stdin-watchdog", daemon=True)
    thread.start()
    return thread
