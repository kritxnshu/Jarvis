"""uvicorn HTTP protocol that drops connections from any other user (peer-UID check)."""

from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from uvicorn.protocols.http.h11_impl import H11Protocol

from jarvis.runtime.peercred import peer_uid

log = logging.getLogger("jarvis.runtime.protocol")


class PeerCheckedH11Protocol(H11Protocol):
    expected_uid: ClassVar[int]

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]
        super().connection_made(transport)
        sock = transport.get_extra_info("socket")
        try:
            uid: int | None = peer_uid(sock)
        except OSError:
            uid = None
        if uid != self.expected_uid:
            log.warning("rejected connection from unexpected peer", extra={"peer_uid": uid})
            transport.close()


def make_peer_checked_protocol(expected_uid: int) -> type[PeerCheckedH11Protocol]:
    return type(
        "BoundPeerCheckedH11Protocol",
        (PeerCheckedH11Protocol,),
        {"expected_uid": expected_uid},
    )
