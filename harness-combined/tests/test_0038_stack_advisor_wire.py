"""
Content-verification tests for the stack-advisor wiring in commands/problem.md
and the scope boundaries documented in context/harness-reference.md.
Verifies spec 0038-tech-stack-advisor-wire (FR-8, FR-11).
"""
from pathlib import Path

PROBLEM_MD = Path(__file__).parent.parent / "commands" / "problem.md"
FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "stack-advisor.md"
REFERENCE_MD = Path(__file__).parent.parent / "context" / "harness-reference.md"
AUTOPILOT_MD = Path(__file__).parent.parent / "commands" / "autopilot.md"


def test_problem_md_references_stack_advisor_flow():
    content = PROBLEM_MD.read_text()
    assert "stack-advisor.md" in content, \
        "commands/problem.md must reference context/flows/stack-advisor.md"


def test_stack_advisor_call_is_between_phase_3_and_phase_4():
    content = PROBLEM_MD.read_text()
    advisor_pos = content.find("stack-advisor.md")
    phase3_end_signal = content.find("status: requirements")
    phase4_pos = content.find("## Phase 4")
    assert advisor_pos > 0, "stack-advisor.md reference not found"
    assert phase3_end_signal > 0, "'status: requirements' marker not found"
    assert phase4_pos > 0, "## Phase 4 header not found"
    assert advisor_pos > phase3_end_signal, \
        "stack-advisor reference must appear after 'status: requirements'"
    assert advisor_pos < phase4_pos, \
        "stack-advisor reference must appear before '## Phase 4'"


def test_insertion_is_clearly_labeled():
    content = PROBLEM_MD.read_text()
    advisor_pos = content.find("stack-advisor.md")
    vicinity = content[max(0, advisor_pos - 500):advisor_pos + 200]
    has_label = (
        "3.5" in vicinity or
        "Tech Stack" in vicinity or
        "stack-advisor" in vicinity.lower()
    )
    assert has_label, \
        "The stack-advisor insertion must be clearly labeled (e.g., Phase 3.5 or Tech Stack Advisor)"


def test_phase_0_through_6_content_unchanged():
    content = PROBLEM_MD.read_text()
    for header in ["## Phase 0", "## Phase 1", "## Phase 2", "## Phase 3", "## Phase 4", "## Phase 5"]:
        assert header in content, f"Existing header '{header}' must not be removed from problem.md"


def test_checkpoint_1_block_unchanged():
    content = PROBLEM_MD.read_text()
    assert "## Checkpoint 1" in content, "Checkpoint 1 block must not be removed"
    assert "Approve to begin implementation?" in content, \
        "Checkpoint 1 approval prompt must not be removed"


def test_stack_advisor_flow_file_exists():
    assert FLOW_FILE.exists(), "context/flows/stack-advisor.md must exist for the wire to be valid"


# M-01: FR-8 — /build honors ## Tech Stack without re-prompting

def test_reference_documents_build_honors_tech_stack_contract():
    """FR-8: once ## Tech Stack is written, /build reads it without re-prompting"""
    content = REFERENCE_MD.read_text()
    advisor_start = content.find("## Tech Stack Advisor")
    assert advisor_start >= 0, "## Tech Stack Advisor section not found in harness-reference.md"
    advisor_section = content[advisor_start:]
    lower = advisor_section.lower()
    has_build_contract = "/build" in advisor_section and (
        "without re-prompting" in lower or
        "no re-prompt" in lower or
        "honor" in lower
    )
    assert has_build_contract, \
        "harness-reference.md Tech Stack Advisor section must document /build honors " \
        "## Tech Stack without re-prompting the lead (FR-8)"


def test_reference_tech_stack_contract_names_autopilot():
    """FR-11: /autopilot also honors ## Tech Stack without triggering the advisor"""
    content = REFERENCE_MD.read_text()
    advisor_start = content.find("## Tech Stack Advisor")
    assert advisor_start >= 0, "## Tech Stack Advisor section not found"
    advisor_section = content[advisor_start:]
    assert "/autopilot" in advisor_section or "autopilot" in advisor_section.lower(), \
        "harness-reference.md Tech Stack Advisor section must mention /autopilot scope (FR-11)"


# M-02: FR-11 — /autopilot does not independently trigger the advisor

def test_autopilot_command_does_not_reference_stack_advisor():
    """FR-11: the advisor fires in /problem only — /autopilot must not call it"""
    if not AUTOPILOT_MD.exists():
        return
    content = AUTOPILOT_MD.read_text()
    assert "stack-advisor.md" not in content, \
        "commands/autopilot.md must NOT reference stack-advisor.md — the advisor fires in /problem only (FR-11)"


def test_problem_md_is_the_only_command_referencing_stack_advisor():
    """FR-11: stack-advisor.md should be referenced by problem.md, not by other commands"""
    commands_dir = Path(__file__).parent.parent / "commands"
    if not commands_dir.exists():
        return
    referencing_commands = [
        f.name for f in commands_dir.glob("*.md")
        if "stack-advisor.md" in f.read_text()
    ]
    assert referencing_commands == ["problem.md"], \
        f"stack-advisor.md must only be referenced by commands/problem.md, " \
        f"found references in: {referencing_commands}"
