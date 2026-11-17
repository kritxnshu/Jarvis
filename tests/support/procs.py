"""Process inspection helpers for security tests (Linux via /proc, macOS via lsof/ps)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def _linux_inet_socket_inodes() -> set[str]:
    inodes: set[str] = set()
    for name in ("tcp", "tcp6", "udp", "udp6"):
        path = Path("/proc/net") / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) > 9:
                inodes.add(fields[9])
    return inodes


def _linux_process_socket_inodes(pid: int) -> set[str]:
    found: set[str] = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        m = re.fullmatch(r"socket:\[(\d+)\]", target)
        if m:
            found.add(m[1])
    return found


def inet_sockets_of(pid: int) -> list[str]:
    if sys.platform.startswith("linux"):
        return sorted(_linux_process_socket_inodes(pid) & _linux_inet_socket_inodes())
    out = subprocess.run(
        ["lsof", "-nP", "-a", "-p", str(pid), "-i"], capture_output=True, text=True, check=False
    )
    return [line for line in out.stdout.splitlines()[1:] if line.strip()]


def argv_and_env(pid: int) -> str:
    if sys.platform.startswith("linux"):
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        environ = Path(f"/proc/{pid}/environ").read_bytes()
        return (cmdline + b"\0" + environ).decode(errors="replace")
    out = subprocess.run(
        ["ps", "-E", "-ww", "-o", "command=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def alive(pid: int) -> bool:
    if sys.platform.startswith("linux"):
        try:
            state = Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0]
        except FileNotFoundError:
            return False
        return state != "Z"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def children_of(pid: int) -> list[int]:
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, check=True
    )
    kids: list[int] = []
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and int(parts[1]) == pid:
            kids.append(int(parts[0]))
    return kids
