"""Content-verification tests for the new commands/autopilot-watch.md
(ticket 0078)."""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent.parent / "commands" / "autopilot-watch.md"


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def test_command_file_exists() -> None:
    assert DOC.exists(), "commands/autopilot-watch.md must exist"


def test_documents_all_three_subcommands() -> None:
    content = _content()
    for subcommand in ("start", "stop", "status"):
        assert f"/autopilot-watch {subcommand}" in content


def test_documents_interval_flag_and_default() -> None:
    content = _content()
    assert "--interval" in content
    assert "30" in content


def test_documents_stop_is_noop_when_not_running() -> None:
    content = _content()
    assert "no-op" in content.lower()


def test_documents_fail_closed_approval_gate() -> None:
    content = _content()
    assert "approved-commit" in content
    assert "ancestor" in content.lower()
    assert "byte-identical" in content.lower() or "content-diff" in content.lower()


def test_documents_single_ticket_and_local_worktree_scope() -> None:
    content = _content()
    assert "batch" in content.lower()
    assert "worktree" in content.lower()


def test_documents_execution_directive() -> None:
    """The doc must actually tell the agent what to run — a prose
    description of what each subcommand does is not an instruction."""
    content = _content()
    assert "## Steps" in content
    assert "bin/autopilot-watch" in content
    assert "$ARGUMENTS" in content
