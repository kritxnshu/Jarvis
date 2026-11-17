"""Structured JSON logging. Redaction runs inside the formatter, so no handler sees raw text."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from jarvis.ids import utc_now_iso
from jarvis.trust.redaction import Redactor

_STD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": utc_now_iso(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = {k: v for k, v in vars(record).items() if k not in _STD_ATTRS}
        if extra:
            entry["fields"] = extra
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return self._redactor.redact(json.dumps(entry, default=str, ensure_ascii=False))


def configure_logging(log_dir: Path, redactor: Redactor, level: int = logging.INFO) -> Path:
    """Send all logging (ours and uvicorn's) as redacted JSON lines to stderr and a file."""
    log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    log_file = log_dir / "backend.jsonl"
    formatter = JsonFormatter(redactor)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    stderr_handler = logging.StreamHandler(sys.stderr)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in (file_handler, stderr_handler):
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    log_file.chmod(0o600)
    return log_file
