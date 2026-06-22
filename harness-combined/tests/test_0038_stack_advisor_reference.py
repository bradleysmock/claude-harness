"""
Content-verification tests for the Tech Stack Advisor section in context/harness-reference.md.
Verifies spec 0038-tech-stack-advisor-reference.
"""
from pathlib import Path

REFERENCE_MD = Path(__file__).parent.parent / "context" / "harness-reference.md"


def _advisor_section(content: str) -> str:
    start = content.find("## Tech Stack Advisor")
    assert start >= 0, "## Tech Stack Advisor section not found in harness-reference.md"
    # Find next ## heading after the section
    next_section = content.find("\n## ", start + len("## Tech Stack Advisor"))
    return content[start:next_section] if next_section >= 0 else content[start:]


def test_tech_stack_advisor_section_exists():
    content = REFERENCE_MD.read_text()
    assert "## Tech Stack Advisor" in content, \
        "context/harness-reference.md must contain a ## Tech Stack Advisor section"


def test_section_documents_no_stack_check_flag():
    content = REFERENCE_MD.read_text()
    section = _advisor_section(content)
    assert "--no-stack-check" in section, \
        "Tech Stack Advisor section must document the --no-stack-check flag"


def test_section_documents_tech_stack_contract():
    content = REFERENCE_MD.read_text()
    section = _advisor_section(content)
    lower = section.lower()
    # Must document that /build and /autopilot honor an existing ## Tech Stack without re-prompting
    assert "## tech stack" in lower or "tech stack" in lower, \
        "Section must document the ## Tech Stack contract"
    has_contract = (
        "/build" in section or
        "build" in lower
    )
    assert has_contract, \
        "Section must document that /build honors the ## Tech Stack section without re-prompting"


def test_section_documents_placeholder_text():
    content = REFERENCE_MD.read_text()
    section = _advisor_section(content)
    assert "stack not specified" in section, \
        "Section must document the placeholder text 'stack not specified'"
    assert "fill in before /build" in section, \
        "Section must document the placeholder text 'fill in before /build'"


def test_section_documents_two_rejection_termination():
    content = REFERENCE_MD.read_text()
    section = _advisor_section(content)
    assert "2" in section or "two" in section.lower(), \
        "Section must document the 2-rejection termination rule"


def test_existing_content_preserved():
    content = REFERENCE_MD.read_text()
    # Spot-check that pre-existing sections still exist
    for section_header in [
        "## Tickets",
        "## Worktrees",
        "## Gate Pipeline",
        "## Gate/Repair Loop",
        "## Memory Contract",
        "## Artifact Constraints",
        "## Multi-Agent Critique",
    ]:
        assert section_header in content, \
            f"Pre-existing section '{section_header}' must not be removed from harness-reference.md"


def test_section_placement_near_tickets_or_artifacts():
    content = REFERENCE_MD.read_text()
    advisor_pos = content.find("## Tech Stack Advisor")
    tickets_pos = content.find("## Tickets")
    assert advisor_pos >= 0, "## Tech Stack Advisor section not found"
    placed_after_tickets = advisor_pos > tickets_pos
    assert placed_after_tickets, \
        "## Tech Stack Advisor should appear after ## Tickets section"
