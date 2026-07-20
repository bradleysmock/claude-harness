"""Content-verification for ticket 0067's critic-brief.md incremental-round branch.

Asserts round 1 / design-review text is unchanged, and the new incremental
branches in Steps 1, 2.5, 3, and 4 carry the required instructions.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CRITIC = (_ROOT / "context" / "critic-brief.md").read_text(encoding="utf-8")


def _section(doc: str, start_marker: str, end_marker: str) -> str:
    start = doc.index(start_marker)
    end = doc.index(end_marker, start + len(start_marker))
    return doc[start:end]


def test_mode_incremental_marker_is_documented() -> None:
    assert "Mode: incremental" in _CRITIC


def test_step_1_scopes_panel_loading_to_diff_touched_files_on_incremental_round() -> None:
    step_1 = _section(_CRITIC, "## Step 1", "## Step 2")
    assert "incremental" in step_1.lower()
    assert "diff" in step_1.lower()
    assert "touched" in step_1.lower()


def test_step_2_5_skips_coverage_and_alignment_on_incremental_round() -> None:
    step_2_5 = _section(_CRITIC, "## Step 2.5", "## Step 3")
    lower = step_2_5.lower()
    assert "incremental" in lower
    assert "skip requirements coverage and solution alignment" in lower


def test_step_2_5_keeps_weakened_tests_check_active_and_diff_scoped_on_incremental_round() -> None:
    step_2_5 = _section(_CRITIC, "## Step 2.5", "## Step 3")
    lower = step_2_5.lower()
    assert "weakened or deleted tests" in lower
    assert "stays active" in lower
    assert "test plan" in lower


def test_step_3_requires_full_scope_prior_finding_reverification() -> None:
    step_3 = _section(_CRITIC, "## Step 3", "## Step 4")
    lower = step_3.lower()
    assert "incremental" in lower
    assert "whether or not that file appears in the diff" in lower


def test_step_4_documents_prior_finding_classification_and_new_finding_scope() -> None:
    step_4 = _section(_CRITIC, "## Step 4", "## Anti-patterns")
    lower = step_4.lower()
    assert "prior-finding classification" in lower
    assert "still-present" in lower
    assert "new findings" in lower
    assert "never marked fixed merely because it falls outside the diff" in lower


def test_round_1_full_scope_language_is_still_present_unchanged() -> None:
    # Round-1 / design-review instructions must remain byte-identical in spirit —
    # spot-check the original anchor phrases survive the incremental additions.
    assert "Read only the panel files for active panels." in _CRITIC
    assert "For **design review** mode, skip this step" in _CRITIC
    assert (
        "Missing implementations and missing tests for stated requirements are "
        "**BLOCKER** findings" in _CRITIC
    )
