"""Canonical action digests. Approvals bind to these (ADR-0004)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8, no NaN/Infinity."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def action_digest(tool: str, tool_version: int, params: dict[str, Any], scope: str = "") -> str:
    """SHA-256 over the exact action. Any change to tool, version, params or scope changes it."""
    body = {"tool": tool, "tool_version": tool_version, "params": params, "scope": scope}
    return hashlib.sha256(canonical_json(body)).hexdigest()
