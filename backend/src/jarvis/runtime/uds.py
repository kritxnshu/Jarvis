"""Binding the backend's Unix domain socket with strict permissions."""

from __future__ import annotations

import os
import socket
import stat
from pathlib import Path

DIR_MODE = 0o700
SOCKET_MODE = 0o600


class SocketSetupError(Exception):
    pass


def check_private_dir(directory: Path) -> None:
    """The socket directory must exist, be owned by us, and be inaccessible to anyone else."""
    try:
        st = directory.lstat()
    except FileNotFoundError:
        raise SocketSetupError(f"socket directory does not exist: {directory}") from None
    if not stat.S_ISDIR(st.st_mode):
        raise SocketSetupError("socket directory is not a directory (or is a symlink)")
    if st.st_uid != os.getuid():
        raise SocketSetupError("socket directory is not owned by the current user")
    if stat.S_IMODE(st.st_mode) != DIR_MODE:
        raise SocketSetupError(
            f"socket directory mode is {stat.S_IMODE(st.st_mode):o}, expected {DIR_MODE:o}"
        )


def bind_unix_socket(path: Path, backlog: int = 64) -> socket.socket:
    check_private_dir(path.parent)
    if path.exists() or path.is_symlink():
        if not stat.S_ISSOCK(path.lstat().st_mode):
            raise SocketSetupError("refusing to replace a non-socket file at the socket path")
        path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o177)
    try:
        sock.bind(str(path))
    except OSError:
        sock.close()
        raise
    finally:
        os.umask(old_umask)
    path.chmod(SOCKET_MODE)
    if stat.S_IMODE(path.stat().st_mode) != SOCKET_MODE:
        sock.close()
        raise SocketSetupError("could not set socket permissions to 0600")
    sock.listen(backlog)
    sock.setblocking(False)
    return sock
