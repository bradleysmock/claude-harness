"""Content-verification tests for harness-reference.md's additive
documentation of the ticket 0078 approval fields + autopilot watcher."""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent.parent / "context" / "harness-reference.md"


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def test_documents_approval_fields_near_status_transitions() -> None:
    content = _content()
    idx = content.index("### Status transitions")
    # scoped to a reasonable window after the table so this doesn't just
    # match an unrelated later mention
    window = content[idx : idx + 6000]
    assert "approved-at" in window
    assert "approved-commit" in window


def test_documents_status_solution_unchanged_by_approval() -> None:
    content = _content()
    idx = content.index("approved-commit")
    window = content[max(0, idx - 2000) : idx + 2000]
    assert "solution" in window
    assert "additive" in window.lower() or "unchanged" in window.lower()


def test_documents_fail_closed_content_diff_gate() -> None:
    content = _content()
    assert "autopilot_watch.py" in content or "autopilot-watch" in content
    assert "ancestor" in content.lower()


def test_preserves_status_transitions_table() -> None:
    content = _content()
    assert "| `solution`" in content
    assert "| `implementing`" in content
