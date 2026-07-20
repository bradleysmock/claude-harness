"""Content-verification for ticket 0067's harness-reference.md documentation."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_REF = (_ROOT / "context" / "harness-reference.md").read_text(encoding="utf-8")


def _section(doc: str, start_marker: str, end_marker: str) -> str:
    start = doc.index(start_marker)
    end = doc.index(end_marker, start + len(start_marker))
    return doc[start:end]


def test_incremental_critic_rounds_section_exists() -> None:
    assert "### Incremental critic rounds (ticket 0067)" in _REF


def test_documents_round_1_and_design_review_stay_full_scope() -> None:
    section = _section(
        _REF,
        "### Incremental critic rounds (ticket 0067)",
        "---",
    )
    assert "full-worktree / full-artifact scope" in section
    assert "unchanged" in section


def test_documents_incremental_scope_module_and_functions() -> None:
    section = _section(_REF, "### Incremental critic rounds (ticket 0067)", "---")
    assert "gates/incremental_scope.py" in section
    assert "touched_files_from_diff" in section
    assert "format_incremental_brief" in section


def test_documents_prior_finding_reverification_never_diff_scoped() -> None:
    section = _section(_REF, "### Incremental critic rounds (ticket 0067)", "---")
    assert "never diff-scoped" in section.lower() or "never be diff-scoped" in section.lower()


def test_documents_fail_closed_fallback() -> None:
    section = _section(_REF, "### Incremental critic rounds (ticket 0067)", "---")
    assert "Fail-closed fallback" in section
    assert "full-scope, unmarked spawn" in section
