"""ULID-style identifiers: 48-bit millisecond timestamp + 80 random bits, Crockford base32."""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id() -> str:
    """Return a 26-character, lexicographically time-sortable identifier."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    chars: list[str] = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with millisecond precision and a Z suffix."""
    now = time.time()
    millis = int(now * 1000) % 1000
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + f".{millis:03d}Z"
