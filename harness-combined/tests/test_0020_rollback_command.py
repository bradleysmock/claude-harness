"""Content-verification tests for commands/rollback.md (ticket 0020).

/rollback is a thin model-interpreted command that delegates the whole procedure to
skills/rollback/SKILL.md. Its substantive behavior is tested in test_0020_rollback_skill.py;
these tests verify the command doc documents the argument contract and the delegation so the
model loads and follows the skill.
"""
from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent.parent / "commands" / "rollback.md"


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def test_command_file_exists() -> None:
    assert DOC.exists(), "commands/rollback.md must exist"


def test_argument_contract_documented() -> None:
    content = _content()
    assert "^[0-9]{4}(-[a-z0-9-]+)?$" in content, "must document the ticket-number pattern"
    assert "required" in content.lower(), "the ticket number must be documented as required"
    assert "--dry-run" in content, "must document the optional --dry-run flag"


def test_delegates_to_skill() -> None:
    content = _content()
    assert "skills/rollback/SKILL.md" in content, "must delegate to skills/rollback/SKILL.md"
    lower = content.lower()
    assert "no logic" in lower, "must state the command holds no logic of its own"


def test_passes_arguments_through() -> None:
    content = _content()
    assert "$ARGUMENTS" in content, "must pass $ARGUMENTS through to the skill"


def test_notes_validation_is_skill_first_step() -> None:
    content = _content().lower()
    assert "first step" in content, "must note that validation is the skill's first step"
    assert "before any git command" in content, \
        "must note that an invalid argument stops before any git command"
