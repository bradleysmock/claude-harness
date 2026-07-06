"""Content-verification tests for commands/sprint.md and skills/sprint/SKILL.md.

The command and skill markdown are LLM-executed, not import-executed, so their
"tests" assert that they document every required behavior per ticket 0035.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
COMMAND_FILE = _ROOT / "commands" / "sprint.md"
SKILL_FILE = _ROOT / "skills" / "sprint" / "SKILL.md"


def _cmd() -> str:
    return COMMAND_FILE.read_text()


def _skill() -> str:
    return SKILL_FILE.read_text()


# ── command entry point ───────────────────────────────────────────────────────

def test_command_file_exists():
    assert COMMAND_FILE.exists(), "commands/sprint.md must exist"


def test_command_documents_all_flags():
    content = _cmd()
    for flag in ("--sprint-capacity", "--max-sprints", "--as-of"):
        assert flag in content, f"flag '{flag}' must be documented"


def test_command_documents_no_arg_invocation():
    # FR-10: /sprint with no arguments produces a default plan.
    content = _cmd().lower()
    assert "no argument" in content or "no arguments" in content


def test_command_delegates_to_skill():
    content = _cmd()
    assert "skills/sprint/SKILL.md" in content
    assert "$ARGUMENTS" in content


def test_command_declares_read_only():
    assert "read-only" in _cmd().lower()


# ── skill procedure ───────────────────────────────────────────────────────────

def test_skill_file_exists():
    assert SKILL_FILE.exists(), "skills/sprint/SKILL.md must exist"


def test_skill_has_frontmatter_name():
    content = _skill()
    assert content.startswith("---")
    assert "name: sprint" in content


def test_skill_invokes_compute_via_stdin_not_shell_arg():
    content = _skill()
    assert "skills/sprint/compute.py" in content
    assert "stdin" in content.lower()
    assert "| python3" in content  # payload piped, never interpolated


def test_skill_collects_open_and_completed_tickets():
    content = _skill()
    assert ".tickets/*/status.md" in content
    assert ".tickets/completed/*/status.md" in content


def test_skill_forbids_eval_and_uses_pipefail():
    content = _skill()
    assert "set -euo pipefail" in content
    assert "no `eval`" in content or "never by parsing `ls`" in content


def test_skill_documents_effort_and_dependency_fields():
    content = _skill().lower()
    assert "effort" in content
    assert "depends-on" in content


def test_skill_documents_sprint_table_columns():
    content = _skill()
    for col in ("Ticket", "Title", "Effort", "Status"):
        assert col in content, f"sprint table column '{col}' must be documented"


def test_skill_documents_capacity_summary():
    assert "capacity" in _skill().lower()


def test_skill_documents_backlog_overflow_section():
    assert "Backlog overflow" in _skill()


def test_skill_documents_cycle_abort_no_partial_plan():
    content = _skill().lower()
    assert "cycle" in content
    assert "partial" in content  # must NOT render a partial plan


def test_skill_documents_empty_message_verbatim():
    assert "No open tickets to plan." in _skill()


def test_skill_declares_read_only_guarantee():
    content = _skill().lower()
    assert "read-only" in content
    assert "never write" in content


def test_skill_documents_no_stack_trace_guarantee():
    content = _skill().lower()
    assert "stack trace" in content
    assert "internal path" in content
