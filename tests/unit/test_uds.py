from __future__ import annotations

import stat
from pathlib import Path

import pytest

from jarvis.runtime.uds import SocketSetupError, bind_unix_socket
from tests.support.backend import make_run_dir


def _dir(tmp_path: Path, mode: int) -> Path:
    d = make_run_dir(tmp_path)
    d.chmod(mode)
    return d


def test_socket_is_0600_in_0700_dir(tmp_path: Path) -> None:
    sock_dir = _dir(tmp_path, 0o700)
    sock = bind_unix_socket(sock_dir / "b.sock")
    try:
        mode = (sock_dir / "b.sock").stat().st_mode
        assert stat.S_ISSOCK(mode)
        assert stat.S_IMODE(mode) == 0o600
    finally:
        sock.close()


@pytest.mark.parametrize("mode", [0o755, 0o750, 0o701, 0o777])
def test_refuses_shared_directory(tmp_path: Path, mode: int) -> None:
    with pytest.raises(SocketSetupError, match="mode"):
        bind_unix_socket(_dir(tmp_path, mode) / "b.sock")


def test_refuses_symlinked_directory(tmp_path: Path) -> None:
    real = _dir(tmp_path, 0o700)
    link = real.parent / f"{real.name}-link"
    link.symlink_to(real)
    with pytest.raises(SocketSetupError, match="symlink"):
        bind_unix_socket(link / "b.sock")


def test_refuses_to_replace_regular_file(tmp_path: Path) -> None:
    d = _dir(tmp_path, 0o700)
    (d / "b.sock").write_text("important")
    with pytest.raises(SocketSetupError, match="non-socket"):
        bind_unix_socket(d / "b.sock")
    assert (d / "b.sock").read_text() == "important"


def test_refuses_overlong_socket_path(tmp_path: Path) -> None:
    d = _dir(tmp_path, 0o700)
    with pytest.raises(SocketSetupError, match="limit"):
        bind_unix_socket(d / ("x" * 120))
