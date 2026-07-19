"""
Content-verification tests for the "## LLM/Python Boundary" section of CLAUDE.md.
Verifies the section's presence, position, anchor phrases, and cited helper paths
per spec 0053-llm-python-boundary-claude-md.
"""
import re
from pathlib import Path

CLAUDE_MD = Path(__file__).parent.parent / "CLAUDE.md"
HEADING = "## LLM/Python Boundary"

PRE_EXISTING_HEADINGS = [
    "## Roles",
    "## Pipeline",
    "## Communication Norms",
    "## Test-Driven Development",
    "## Code Generation Rules",
    "## Reference",
]

_PLUGIN_ROOT_TOKEN_RE = re.compile(r"`\$\{CLAUDE_PLUGIN_ROOT\}/([^`]+)`")


def _section_from(content: str, start_header: str, end_header: str | None = None) -> str:
    """Extract a section from start_header to end_header (or end of file if end_header is None)."""
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


def _top_level_headings(content: str) -> list[str]:
    return [line.strip() for line in content.splitlines() if line.startswith("## ")]


def test_heading_occurs_exactly_once():
    content = CLAUDE_MD.read_text()
    assert content.count(HEADING) == 1, f"'{HEADING}' must occur exactly once in CLAUDE.md"


def test_heading_positioned_between_code_generation_rules_and_reference():
    content = CLAUDE_MD.read_text()
    headings = _top_level_headings(content)
    assert HEADING in headings
    idx = headings.index(HEADING)
    assert headings[idx - 1] == "## Code Generation Rules", (
        "'## LLM/Python Boundary' must immediately follow '## Code Generation Rules'"
    )
    assert headings[idx + 1] == "## Reference", (
        "'## LLM/Python Boundary' must immediately precede '## Reference'"
    )


def test_pre_existing_headings_present_in_original_order():
    content = CLAUDE_MD.read_text()
    headings = _top_level_headings(content)
    positions = [headings.index(h) for h in PRE_EXISTING_HEADINGS]
    assert positions == sorted(positions), (
        "All pre-existing '## ' headings must remain present and in original relative order"
    )


def test_section_states_pass_fail_authority_implemented_in_python():
    content = CLAUDE_MD.read_text()
    section = _section_from(content, HEADING, "## Reference")
    assert "pass/fail authority" in section
    assert "implemented in Python" in section


def test_section_states_exactness_operations():
    content = CLAUDE_MD.read_text()
    section = _section_from(content, HEADING, "## Reference")
    assert "exactness operations" in section


def test_section_defines_judgment_only_role_without_override():
    content = CLAUDE_MD.read_text()
    section = _section_from(content, HEADING, "## Reference")
    assert "judgment only" in section
    assert "never re-derives or overrides" in section


def test_section_includes_decision_test_sentence():
    content = CLAUDE_MD.read_text()
    section = _section_from(content, HEADING, "## Reference")
    assert "if two runs must agree on the answer, it belongs in Python" in section


def test_section_states_fail_closed_rule():
    content = CLAUDE_MD.read_text()
    section = _section_from(content, HEADING, "## Reference")
    assert "never substitutes its own judgment" in section


def test_section_cites_at_least_3_existing_helper_paths():
    content = CLAUDE_MD.read_text()
    section = _section_from(content, HEADING, "## Reference")
    project_root = CLAUDE_MD.parent
    cited = _PLUGIN_ROOT_TOKEN_RE.findall(section)
    existing = [p for p in cited if (project_root / p).exists()]
    assert len(existing) >= 3, (
        f"Section must cite >= 3 existing helper paths via ${{CLAUDE_PLUGIN_ROOT}}/..., found {existing}"
    )


def test_section_line_count_within_budget():
    content = CLAUDE_MD.read_text()
    section = _section_from(content, HEADING, "## Reference")
    # Trim the trailing '---' separator line that _section_from includes up to the next heading.
    lines = [line for line in section.splitlines() if line.strip() != "---"]
    assert len(lines) <= 25, (
        f"'## LLM/Python Boundary' section must be <= 25 lines, found {len(lines)}"
    )
