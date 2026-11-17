"""Peer credentials for Unix domain sockets (who is on the other end of a connection)."""

from __future__ import annotations

import socket
import struct
import sys
from typing import Protocol


class _SockOpt(Protocol):
    def getsockopt(self, level: int, optname: int, buflen: int, /) -> bytes: ...


# macOS <sys/un.h>: SOL_LOCAL = 0, LOCAL_PEERCRED = 0x001; returns struct xucred
# { u_int cr_version; uid_t cr_uid; short cr_ngroups; gid_t cr_groups[16]; }
_SOL_LOCAL = 0
_LOCAL_PEERCRED = 0x001
_XUCRED_SIZE = 4 + 4 + 2 + 2 + 16 * 4


class PeerCredUnsupportedError(OSError):
    pass


def peer_uid(sock: _SockOpt) -> int:
    """Return the effective UID of the process connected to ``sock``."""
    if sys.platform.startswith("linux"):
        so_peercred: int = getattr(socket, "SO_PEERCRED", 17)
        data = sock.getsockopt(socket.SOL_SOCKET, so_peercred, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", data)
        return int(uid)
    if sys.platform == "darwin":
        data = sock.getsockopt(_SOL_LOCAL, _LOCAL_PEERCRED, _XUCRED_SIZE)
        _version, uid = struct.unpack_from("II", data)
        return int(uid)
    raise PeerCredUnsupportedError(f"peer credentials not implemented for {sys.platform}")
