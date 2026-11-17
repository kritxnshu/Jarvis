"""Crash-safe local file operations (BRIEF §5.5).

A crash at any point leaves either the old state or the complete new state — never a partial
or missing file. The file tool (M5) builds on these.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable
from pathlib import Path

Hook = Callable[[], None]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, *, before_replace: Hook | None = None) -> str:
    """Write ``data`` to ``path`` atomically; returns the SHA-256 of what is now on disk."""
    tmp = path.with_name(f".{path.name}.jarvis-tmp-{os.getpid()}")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    if path.exists():
        shutil.copymode(path, tmp)
    if before_replace:
        before_replace()
    os.replace(tmp, path)
    _fsync_dir(path.parent)
    return sha256_file(path)


class MoveVerificationError(OSError):
    pass


def safe_move(
    src: Path, dst: Path, *, force_copy: bool = False, after_copy: Hook | None = None
) -> str:
    """Move ``src`` to ``dst``. Same volume: atomic rename. Across volumes: copy to a temp
    name, fsync, verify the hash, rename into place, and only then delete the source."""
    if dst.exists():
        raise FileExistsError(str(dst))
    expected = sha256_file(src)
    if not force_copy:
        try:
            os.rename(src, dst)
            _fsync_dir(dst.parent)
            return expected
        except OSError as exc:
            if exc.errno != 18:  # EXDEV: cross-device link
                raise
    tmp = dst.with_name(f".{dst.name}.jarvis-tmp-{os.getpid()}")
    shutil.copy2(src, tmp)
    with tmp.open("rb+") as fh:
        os.fsync(fh.fileno())
    if sha256_file(tmp) != expected:
        tmp.unlink(missing_ok=True)
        raise MoveVerificationError(f"copy of {src} does not match the source")
    os.replace(tmp, dst)
    _fsync_dir(dst.parent)
    if after_copy:
        after_copy()
    os.unlink(src)
    _fsync_dir(src.parent)
    return expected
