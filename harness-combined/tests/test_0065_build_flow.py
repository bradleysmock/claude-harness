"""Content-verification tests for context/flows/build-ticket.md (ticket 0065).

Verifies Step 4 documents the TDD-order split — write the test first, run a
red-gate check scoped to the new test node id(s), classify red/blocking/
tool_error, then on red write implementation directly — and no longer
instructs generating implementation and tests together into fenced
`# implementation` / `# tests` blocks. Template: tests/test_0014_build_flow.py.
"""
from pathlib import Path

FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "build-ticket.md"


def _section_from(content: str, start_header: str, end_header: str | None = None) -> str:
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


def test_flow_file_exists() -> None:
    assert FLOW_FILE.exists()


def test_step4_no_longer_generates_fenced_implementation_and_tests_together() -> None:
    content = FLOW_FILE.read_text()
    step4 = _section_from(content, "## Step 4", "## Step 5")
    assert "Generate implementation and tests" not in step4, \
        "Step 4 must no longer instruct generating implementation and tests together"
    assert "no fenced" in step4, \
        "Step 4 must state writes are direct, not into fenced blocks"


def test_step4_writes_test_before_implementation() -> None:
    content = FLOW_FILE.read_text()
    step4 = _section_from(content, "## Step 4", "## Step 5")
    write_test_pos = step4.find("Write the spec's test source")
    write_impl_pos = step4.find("Write the spec's implementation source")
    assert write_test_pos >= 0, "Step 4 must document writing the test file directly"
    assert write_impl_pos >= 0, "Step 4 must document writing the implementation file directly"
    assert write_test_pos < write_impl_pos, \
        "the test must be written before the implementation in Step 4's ordering"


def test_step4_documents_red_gate_check() -> None:
    content = FLOW_FILE.read_text()
    step4 = _section_from(content, "## Step 4", "## Step 5")
    assert "gate_run_red_check" in step4, "Step 4 must call the gate_run_red_check tool"
    assert "node_ids" in step4


def test_step4_documents_all_three_classifications_and_actions() -> None:
    content = FLOW_FILE.read_text()
    step4 = _section_from(content, "## Step 4", "## Step 5")
    for token in ("`proceed`", "`retry`", "`escalate_skip`"):
        assert token in step4, f"Step 4 must document the {token} action"
    for token in ("`red`", "`blocking`", "`tool_error`"):
        assert token in step4, f"Step 4 must document the {token} classification"


def test_step4_documents_budget_reuses_max_repair_attempts() -> None:
    content = FLOW_FILE.read_text()
    step4 = _section_from(content, "## Step 4", "## Step 5")
    assert "MAX_REPAIR_ATTEMPTS" in step4


def test_step4_documents_skip_and_continue_on_escalation() -> None:
    content = FLOW_FILE.read_text()
    step4 = _section_from(content, "## Step 4", "## Step 5")
    lower = step4.lower()
    assert "skip implementation for this spec" in lower
    assert "continue" in lower and "next spec" in lower


def test_step4e_gate_repair_loop_still_documented_unchanged() -> None:
    """Step 4e's gate_run_on_dir full-suite repair loop (now relettered 4f under
    the new sub-step split) must still exist, untouched, as the final pass/fail
    authority — FR-8."""
    content = FLOW_FILE.read_text()
    step4 = _section_from(content, "## Step 4", "## Step 5")
    assert "gate_run_on_dir" in step4
    assert "MAX_REPAIR_ATTEMPTS" in step4
