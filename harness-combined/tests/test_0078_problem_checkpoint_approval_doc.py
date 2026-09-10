"""Content-verification tests for commands/problem.md's Checkpoint 1 wiring
(ticket 0078). Approving at Checkpoint 1 must persist `approved-at` +
`approved-commit` on the branch — additive only, `status` itself stays
`solution` — and the session-boundary note must mention the watcher.
"""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent.parent / "commands" / "problem.md"


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def _checkpoint_section() -> str:
    content = _content()
    start = content.index("## Checkpoint 1 — Present to Lead")
    return content[start:]


def test_checkpoint_documents_approval_fields() -> None:
    section = _checkpoint_section()
    assert "approved-at" in section
    assert "approved-commit" in section
    assert '"yes" only' in section or "on “yes” only" in section.lower() or "yes\" only" in section


def test_checkpoint_documents_additive_status_unchanged() -> None:
    section = _checkpoint_section()
    assert "status" in section
    assert "solution" in section
    assert "additive" in section.lower()


def test_checkpoint_documents_no_feedback_leaves_fields_blank() -> None:
    section = _checkpoint_section()
    lowered = section.lower()
    assert "blank" in lowered
    assert '"no"' in lowered or "feedback" in lowered


def test_checkpoint_commits_on_branch_never_main() -> None:
    section = _checkpoint_section()
    assert 'git -C .worktrees/XXXX-<slug> commit' in section
    assert 'git -C .worktrees/XXXX-<slug> push' in section


def test_session_boundary_mentions_watcher() -> None:
    section = _checkpoint_section()
    note = section[section.index("**Session boundary**") :]
    assert "autopilot-watch" in note or "autopilot_watch" in note


def test_preserves_approve_prompt_and_do_not_proceed() -> None:
    section = _checkpoint_section()
    assert "Approve to begin implementation? (yes / no / feedback)" in section
    assert "Do not proceed until the lead approves." in section
