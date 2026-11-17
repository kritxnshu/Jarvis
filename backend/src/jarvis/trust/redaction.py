"""Central secret redaction. Everything written to logs, the database or exports passes here."""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping, Sequence
from typing import Any, cast

REDACTED = "[REDACTED]"

# Known secret shapes. Generous on purpose: a false positive costs a log line, a false
# negative leaks a credential.
SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # OpenAI, Anthropic (sk-ant-...), test canary. Not inside words like "high-risk-approval".
    re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google API keys
    re.compile(r"\bA(?:KIA|SIA)[0-9A-Z]{16}\b"),  # AWS access key ids
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),  # Slack
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{16,}=*"),
)

_MIN_REGISTERED_LEN = 8


class Redactor:
    """Redacts known secret patterns plus exact values registered at runtime."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._exact: tuple[str, ...] = ()

    def register(self, secret: str) -> None:
        """Register an exact secret value (e.g. the launch secret, a stored API key)."""
        if len(secret) < _MIN_REGISTERED_LEN:
            raise ValueError("refusing to register a secret shorter than 8 characters")
        with self._lock:
            if secret not in self._exact:
                # Longest first so overlapping secrets are fully removed.
                self._exact = tuple(sorted((*self._exact, secret), key=len, reverse=True))

    def redact(self, text: str) -> str:
        for secret in self._exact:
            if secret in text:
                text = text.replace(secret, REDACTED)
        for pattern in SECRET_PATTERNS:
            text = pattern.sub(REDACTED, text)
        return text

    def redact_value(self, value: Any) -> Any:
        """Recursively redact strings inside JSON-like structures."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, Mapping):
            items = cast("Mapping[Any, Any]", value)
            return {self.redact(str(k)): self.redact_value(v) for k, v in items.items()}
        if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
            seq = cast("Sequence[Any]", value)
            return [self.redact_value(v) for v in seq]
        return value
