"""Content-verification tests for the /health command + skill (ticket 0016).

These target the markdown instruction files (commands/health.md, skills/health/SKILL.md),
not Python — they assert the structural substrings that make the command a thin,
read-only entry point wired to health.py. The module's behavior is covered by
tests/test_health.py.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent

COMMAND = ROOT / "commands" / "health.md"
SKILL = ROOT / "skills" / "health" / "SKILL.md"


def test_command_file_exists_and_invokes_skill():
    text = COMMAND.read_text(encoding="utf-8")
    assert "health" in text.lower()
    assert "skill" in text.lower()  # delegates to the skill, not inline logic
    assert "read-only" in text.lower()


def test_skill_frontmatter_names_health():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---")
    # frontmatter block with name: health
    fm = text.split("---", 2)[1]
    assert "name: health" in fm
    assert "TRIGGER" in fm  # description carries a trigger cue


def test_skill_wires_module_entry_points():
    text = SKILL.read_text(encoding="utf-8")
    assert "health.py" in text
    assert "health_report" in text
    assert "format_report" in text
    assert "stdout" in text
    assert "read-only" in text.lower()


def test_skill_documents_readonly_and_exit_contract():
    text = SKILL.read_text(encoding="utf-8")
    assert "memory.db" in text
    # exit-code contract surfaced for the lead
    assert "non-zero" in text or "exit" in text.lower()
