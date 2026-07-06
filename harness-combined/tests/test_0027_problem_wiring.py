"""Content-verification tests for commands/problem.md wiring (ticket 0027).

/problem is a model-interpreted command. Ticket 0027 wires the ticket_templates.py
building blocks into it. These tests assert the command doc documents the --type
flag, description inference, template + custom-section injection, per-artifact line
limits, and the status.md type: field — while preserving the original phase
structure and scaffold blocks (no regression).
"""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent.parent / "commands" / "problem.md"


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def test_command_file_exists() -> None:
    assert DOC.exists(), "commands/problem.md must exist"


def test_documents_type_flag_with_allow_list_validation() -> None:
    content = _content()
    assert "--type" in content, "must document the --type flag"
    assert "ticket_templates.validate_type" in content, "must cite validate_type"
    for category in ("bug", "feature", "refactor"):
        assert category in content, f"allow-list must mention {category}"


def test_documents_description_inference() -> None:
    content = _content()
    assert "ticket_templates.infer_category" in content
    assert "low-confidence" in content.lower() or "ambiguous" in content.lower()


def test_documents_template_loading() -> None:
    content = _content()
    assert "ticket_templates.load_template" in content
    assert "_templates/" in content, "must reference the _templates/ directory"
    # Missing/empty template must fall back without crashing.
    assert "generic scaffold" in content.lower()


def test_documents_custom_section_injection_into_all_three_artifacts() -> None:
    content = _content()
    assert "ticket_templates.load_custom_sections" in content
    assert "## Custom Sections" in content
    for artifact in ("problem.md", "requirements.md", "solution.md"):
        assert artifact in content, f"custom sections must reach {artifact}"


def test_documents_additive_injection_and_line_limits() -> None:
    content = _content()
    assert "ticket_templates.merge_sections" in content
    assert "additive" in content.lower()
    assert "ticket_templates.enforce_line_limit" in content
    for limit in ("40", "60", "80"):
        assert limit in content, f"must document the {limit}-line limit"


def test_documents_status_type_field_cases() -> None:
    content = _content()
    assert "ticket_templates.format_type_field" in content
    assert "type: <category>" in content
    assert "(inferred)" in content
    assert "type: generic" in content


def test_preserves_original_phase_structure() -> None:
    content = _content()
    for phase in (
        "## Phase 0 — Clarity Check",
        "## Phase 2 — Problem",
        "## Phase 3 — Requirements",
        "## Phase 4 — Solution",
        "## Phase 5 — Critic Loop",
        "## Checkpoint 1 — Present to Lead",
    ):
        assert phase in content, f"original section {phase!r} must remain"


def test_preserves_scaffold_blocks_no_regression() -> None:
    content = _content()
    for block in ("# Problem Statement", "# Requirements", "# Solution", "status: solution"):
        assert block in content, f"scaffold block {block!r} must remain (no regression)"


def test_preserves_fail_closed_standards_gate() -> None:
    content = _content()
    assert "standards_validator.py" in content, "the fail-closed standards gate must remain"
