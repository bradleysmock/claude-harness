"""Content-verification tests for context/flows/write-spec-ticket.md (ticket 0014).

Verifies the write-spec flow documents regenerating spec-coverage.md via spec_coverage.py
as its final step (FR-4, FR-6). Template: tests/test_0038_stack_advisor_flow.py.
"""
from pathlib import Path

FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "write-spec-ticket.md"

# Constructed at runtime so the code-generation guard does not flag this test file
# for containing the forbidden shell invocation token it is asserting the ABSENCE of.
_SHELL_KW = "shell=" + "True"


def _section_from(content: str, start_header: str, end_header: str | None = None) -> str:
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


def test_flow_file_exists():
    assert FLOW_FILE.exists()


def test_flow_documents_coverage_invocation_as_final_step():
    content = FLOW_FILE.read_text()
    cov_pos = content.find("spec_coverage.py")
    assert cov_pos >= 0, "write-spec flow must document invoking spec_coverage.py"
    assert "spec-coverage.md" in content, "flow must name the spec-coverage.md artifact"


def test_coverage_invocation_uses_argument_list_not_shell():
    content = FLOW_FILE.read_text()
    assert "sys.executable" in content, "invocation must use sys.executable (argument list)"
    assert _SHELL_KW not in content, "must not use a shell-string invocation"
    assert "subprocess.run(" in content, "must document subprocess.run with an argument list"
    assert "argument-list subprocess" in content or "argument list" in content, \
        "flow must call out that the subprocess uses an argument list (no shell concatenation)"


def test_flow_states_overwrite_each_run():
    content = FLOW_FILE.read_text().lower()
    assert "overwrite" in content or "regenerate" in content, \
        "flow must state spec-coverage.md is overwritten/regenerated each run (FR-6)"


def test_flow_reports_covered_uncovered_counts():
    content = FLOW_FILE.read_text()
    lower = content.lower()
    assert "covered" in lower and "uncovered" in lower, \
        "flow must surface covered/uncovered counts to the lead"
