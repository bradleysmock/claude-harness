"""Content-verification for the /flaky command spec (commands/flaky.md).

Markdown command specs are 'tested' by asserting the structural substrings a
correct spec must contain (mirroring tests/test_0038_stack_advisor_flow.py).
"""

from __future__ import annotations

from pathlib import Path

_DOC = (Path(__file__).resolve().parent.parent / "commands" / "flaky.md").read_text(encoding="utf-8")


def test_documents_runs_argument_default_5() -> None:
    assert "--runs" in _DOC
    assert "default `5`" in _DOC


def test_documents_threshold_argument_and_range() -> None:
    assert "--threshold" in _DOC
    assert "0.0" in _DOC and "1.0" in _DOC


def test_names_both_report_artifacts() -> None:
    assert "flaky-report.json" in _DOC
    assert "flaky-report.md" in _DOC


def test_references_run_detection_engine() -> None:
    assert "run_detection" in _DOC


def test_states_all_pass_and_all_fail_are_not_flaky() -> None:
    lower = _DOC.lower()
    assert "all" in lower and "not" in lower
    assert "passes in **all** runs" in _DOC
    assert "fails in **all** runs" in _DOC
