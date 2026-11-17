from __future__ import annotations

import io
import threading

from jarvis.runtime.watchdog import start_stdin_watchdog


def test_eof_requests_shutdown_then_hard_exit() -> None:
    shutdown = threading.Event()
    exited: list[int] = []
    done = threading.Event()

    def hard_exit(code: int) -> None:
        exited.append(code)
        done.set()

    start_stdin_watchdog(io.BytesIO(b"ignored data"), shutdown.set, 0.05, hard_exit)
    assert shutdown.wait(2)
    assert done.wait(2)
    assert exited == [0]
