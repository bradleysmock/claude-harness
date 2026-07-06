"""Content-verification tests for commands/velocity.md.

The command markdown is LLM-executed, not import-executed, so its "tests" assert
that it documents every required behavior per spec 0021-velocity-report-command.
"""

from __future__ import annotations

from pathlib import Path

COMMAND_FILE = Path(__file__).resolve().parents[2] / "commands" / "velocity.md"


def _content() -> str:
    return COMMAND_FILE.read_text()


def test_command_file_exists():
    assert COMMAND_FILE.exists(), "commands/velocity.md must exist"


def test_invokes_compute_helper_via_stdin():
    content = _content()
    assert "skills/velocity/compute.py" in content
    assert "stdin" in content.lower()
    # Data must be piped, never passed as a shell argument.
    assert "| python3" in content


def test_documents_per_ticket_table_columns():
    content = _content()
    for col in ("Ticket", "Title", "Start", "Done", "Cycle Time (days)"):
        assert col in content, f"per-ticket column '{col}' must be documented"


def test_documents_weekly_table_columns():
    content = _content()
    for col in ("Week", "Tickets", "Avg Cycle Time (days)", "Min", "Max"):
        assert col in content, f"weekly column '{col}' must be documented"


def test_documents_overall_average():
    assert "overall" in _content().lower()


def test_documents_empty_message_verbatim():
    assert "No completed tickets found." in _content()


def test_documents_skip_and_report():
    content = _content().lower()
    assert "malformed" in content
    assert "invalid date range" in content
    assert "skip" in content


def test_documents_path_containment():
    content = _content()
    assert "Path.resolve()" in content
    assert "containment" in content.lower() or "contained" in content.lower()


def test_documents_start_date_creation_proxy_caveat():
    content = _content().lower()
    assert "creation" in content or "authoring" in content
    assert "not" in content and "status-transition" in content


def test_documents_no_stack_trace_guarantee():
    content = _content().lower()
    assert "stack trace" in content
    assert "internal path" in content


def test_documents_iso_week_year_boundary_semantics():
    content = _content()
    assert "2020-W53" in content or "W53" in content
    assert "ISO 8601" in content or "ISO" in content
