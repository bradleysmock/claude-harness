"""Tests for gates.finding.finding_key (ticket 0062)."""

from __future__ import annotations

from gates.comment_deduplicator import critic_hash
from gates.finding import Finding, finding_key


def _f(**overrides: object) -> Finding:
    base = dict(file="src/module.py", line=12, severity="BLOCKER", code="Security / Injection", message="body")
    base.update(overrides)
    return Finding(**base)


def test_finding_key_returns_the_four_field_tuple() -> None:
    f = _f()
    assert finding_key(f) == (f.file, f.line, f.severity, f.code)


def test_finding_key_handles_none_line_and_empty_code() -> None:
    f = _f(line=None, code="")
    assert finding_key(f) == ("src/module.py", None, "BLOCKER", "")


def test_finding_key_is_message_independent() -> None:
    a = _f(message="one message")
    b = _f(message="a completely different message")
    assert finding_key(a) == finding_key(b)


def test_critic_hash_matches_hash_of_finding_key_fields() -> None:
    f = _f()
    file_, line_, severity_, code_ = finding_key(f)
    import hashlib

    expected = hashlib.sha256(f"{file_}:{line_}:{severity_}:{code_}".encode("utf-8")).hexdigest()
    assert critic_hash(f) == expected
