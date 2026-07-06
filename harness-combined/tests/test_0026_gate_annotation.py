"""Content-verification for the /gate flaky-annotation step (commands/gate.md).

Asserts the gate command documents loading the flaky report, in-memory annotation
before the single findings write, the 'known flaky (X/N)' label, and the fail-closed
rule for an absent/unparseable report.
"""

from __future__ import annotations

from pathlib import Path

_DOC = (Path(__file__).resolve().parent.parent / "commands" / "gate.md").read_text(encoding="utf-8")


def test_documents_loading_flaky_report() -> None:
    assert "flaky-report.json" in _DOC


def test_documents_annotate_failures_call() -> None:
    assert "annotate_failures" in _DOC


def test_documents_in_memory_before_single_write() -> None:
    lower = _DOC.lower()
    assert "in-memory" in lower
    assert "single" in lower or "atomic" in lower


def test_documents_known_flaky_label() -> None:
    assert "known flaky (X/N)" in _DOC


def test_documents_fail_closed_rule() -> None:
    lower = _DOC.lower()
    assert "fail closed" in lower or "fail-closed" in lower
    assert "hard blocker" in lower
    assert "absent" in lower or "unparseable" in lower or "malformed" in lower
