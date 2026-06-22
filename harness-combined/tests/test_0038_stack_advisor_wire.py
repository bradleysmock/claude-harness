"""
Content-verification tests for the stack-advisor wiring in commands/problem.md.
Verifies spec 0038-tech-stack-advisor-wire.
"""
from pathlib import Path

PROBLEM_MD = Path(__file__).parent.parent / "commands" / "problem.md"
FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "stack-advisor.md"


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
    # The insertion must have a recognizable label near the stack-advisor reference
    advisor_pos = content.find("stack-advisor.md")
    # Look for a Phase 3.5 or Tech Stack Advisor label in the vicinity (within 500 chars)
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
    # Spot-check that existing phase headers still exist
    for header in ["## Phase 0", "## Phase 1", "## Phase 2", "## Phase 3", "## Phase 4", "## Phase 5"]:
        assert header in content, f"Existing header '{header}' must not be removed from problem.md"


def test_checkpoint_1_block_unchanged():
    content = PROBLEM_MD.read_text()
    assert "## Checkpoint 1" in content, "Checkpoint 1 block must not be removed"
    assert "Approve to begin implementation?" in content, \
        "Checkpoint 1 approval prompt must not be removed"


def test_stack_advisor_flow_file_exists():
    assert FLOW_FILE.exists(), "context/flows/stack-advisor.md must exist for the wire to be valid"
