"""Content-verification tests for the ticket 0031 prose updates.

Markdown deliverables (command + skill docs) are "tested" by asserting the
structural substrings that document the ``--comment`` opt-in are present.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_gate_command_documents_comment_flag() -> None:
    text = (_ROOT / "commands" / "gate.md").read_text(encoding="utf-8")
    assert "--comment" in text
    assert "post_findings" in text
    assert "should_post=True" in text
    assert "kind=\"gate\"" in text


def test_critique_skill_documents_comment_flag() -> None:
    text = (_ROOT / "skills" / "critique" / "SKILL.md").read_text(encoding="utf-8")
    assert "--comment" in text
    assert "parse_critic_findings" in text
    assert "kind=\"critic\"" in text
    assert "[suggestion]" in text
