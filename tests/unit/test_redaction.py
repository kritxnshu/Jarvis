from __future__ import annotations

import pytest

from jarvis.trust.redaction import REDACTED, Redactor
from tests.conftest import CANARY


@pytest.mark.parametrize(
    "secret",
    [
        CANARY,
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",  # secret-scan: allow
        "sk-proj-ABCDEFGHIJKLMNOP1234",  # secret-scan: allow
        "AIzaSyA1234567890abcdefghijklmnopqrst",  # secret-scan: allow
        "AKIAABCDEFGHIJKLMNOP",  # secret-scan: allow
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",  # secret-scan: allow
        "xoxb-1234567890-abcdefghij",  # secret-scan: allow
        "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n"  # secret-scan: allow
        "-----END RSA PRIVATE KEY-----",
        "Bearer abcdefghijklmnopqrstuvwxyz",  # secret-scan: allow
    ],
)
def test_known_patterns_are_redacted(secret: str) -> None:
    out = Redactor().redact(f"before {secret} after")
    assert secret not in out
    assert REDACTED in out
    assert out.startswith("before ")
    assert out.endswith(" after")


def test_registered_exact_secret_is_redacted() -> None:
    r = Redactor()
    value = "0123456789abcdef" * 4
    r.register(value)
    assert r.redact(f"x{value}y") == f"x{REDACTED}y"


def test_short_secrets_cannot_be_registered() -> None:
    with pytest.raises(ValueError, match="shorter"):
        Redactor().register("abc")


def test_redact_value_walks_nested_structures() -> None:
    data = {"k": [CANARY, {"inner": f"key={CANARY}"}], CANARY: 1, "n": 5}
    out = Redactor().redact_value(data)
    assert CANARY not in repr(out)
    assert out["n"] == 5


def test_plain_text_is_untouched() -> None:
    text = "settings updated: appearance.reduced_motion=on"
    assert Redactor().redact(text) == text


@pytest.mark.parametrize(
    "text", ["confirm_high_risk_approval", "allow-confirm-high-risk-approval", "disk-utilities-x"]
)
def test_words_containing_sk_dash_are_not_secrets(text: str) -> None:
    assert Redactor().redact(text) == text
