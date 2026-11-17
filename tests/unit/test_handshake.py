from __future__ import annotations

import io
import json

import pytest

from jarvis.runtime.handshake import MAX_HANDSHAKE_BYTES, HandshakeError, read_launch_config

SECRET = "ab" * 32


def _stream(obj: object) -> io.BytesIO:
    return io.BytesIO((json.dumps(obj) + "\n").encode())


def test_valid_handshake() -> None:
    cfg = read_launch_config(
        _stream({"secret": SECRET, "socket_path": "/tmp/r/s.sock", "data_dir": "/tmp/d"})
    )
    assert cfg.secret == SECRET
    assert SECRET not in repr(cfg)


@pytest.mark.parametrize("bad_secret", ["AB" * 32, "ab" * 31, "zz" * 32, "", "ab" * 32 + "\u0000"])
def test_invalid_secret_is_rejected_without_echo(bad_secret: str) -> None:
    with pytest.raises(HandshakeError) as info:
        read_launch_config(
            _stream({"secret": bad_secret, "socket_path": "/tmp/s", "data_dir": "/tmp/d"})
        )
    if bad_secret:
        assert bad_secret not in str(info.value)


def test_relative_paths_rejected() -> None:
    with pytest.raises(HandshakeError, match="absolute"):
        read_launch_config(_stream({"secret": SECRET, "socket_path": "s.sock", "data_dir": "d"}))


def test_extra_fields_rejected() -> None:
    with pytest.raises(HandshakeError, match="extra"):
        read_launch_config(
            _stream({"secret": SECRET, "socket_path": "/s", "data_dir": "/d", "x": 1})
        )


def test_eof_and_garbage_and_oversize() -> None:
    with pytest.raises(HandshakeError, match="closed"):
        read_launch_config(io.BytesIO(b""))
    with pytest.raises(HandshakeError, match="JSON"):
        read_launch_config(io.BytesIO(b"not json\n"))
    with pytest.raises(HandshakeError, match="too long"):
        read_launch_config(io.BytesIO(b"x" * (MAX_HANDSHAKE_BYTES + 10) + b"\n"))
