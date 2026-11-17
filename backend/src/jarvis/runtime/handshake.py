"""Launch handshake: the Rust shell writes one JSON line on stdin with the launch secret.

The secret never travels through argv or the environment, which other processes can read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_HANDSHAKE_BYTES = 8192


class HandshakeError(Exception):
    """Raised for any malformed handshake. Messages never include the input values."""


class LaunchConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    secret: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    socket_path: Path
    data_dir: Path


def read_launch_config(stream: BinaryIO) -> LaunchConfig:
    line = stream.readline(MAX_HANDSHAKE_BYTES)
    if not line:
        raise HandshakeError("stdin closed before the launch handshake arrived")
    if not line.endswith(b"\n"):
        raise HandshakeError("handshake line too long or not newline-terminated")
    try:
        raw = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HandshakeError("handshake is not valid JSON") from None
    try:
        config = LaunchConfig.model_validate(raw)
    except ValidationError as exc:
        # Report only field locations and error types, never the offending input.
        problems = ", ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<root>'}:{e['type']}" for e in exc.errors()
        )
        raise HandshakeError(f"invalid handshake fields: {problems}") from None
    if not config.socket_path.is_absolute() or not config.data_dir.is_absolute():
        raise HandshakeError("socket_path and data_dir must be absolute")
    return config
