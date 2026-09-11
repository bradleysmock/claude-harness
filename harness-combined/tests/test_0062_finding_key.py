"""Tests for gates.finding.finding_key (ticket 0062)."""

from __future__ import annotations

from gates.comment_deduplicator import critic_hash
from gates.finding import Finding, finding_key


def _f(
    *,
    file: str = "src/module.py",
    line: int | None = 12,
    severity: str = "BLOCKER",
    code: str = "Security / Injection",
    message: str = "body",
) -> Finding:
    """A ``Finding`` with the fields under test overridden by keyword.

    One declared parameter per ``Finding`` field, rather than a ``**overrides``
    catch-all: unpacking a ``dict[str, object]`` into the constructor erases
    every field type, which is exactly what mypy reported here.
    """
    return Finding(file=file, line=line, severity=severity, code=code, message=message)


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
