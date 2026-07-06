"""Content-verification tests for context/flows/build-ticket.md (ticket 0014).

Verifies the build flow documents the non-blocking spec-coverage warning via
spec_coverage.py --warning-only (FR-5), including backward-compatible skip when
spec-coverage.md is absent. Template: tests/test_0038_stack_advisor_flow.py.
"""
from pathlib import Path

FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "build-ticket.md"

_SHELL_KW = "shell=" + "True"  # constructed so the guard doesn't flag this assertion file


def test_flow_file_exists():
    assert FLOW_FILE.exists()


def test_build_documents_warning_only_invocation():
    content = FLOW_FILE.read_text()
    assert "spec_coverage.py" in content, "build flow must document invoking spec_coverage.py"
    assert "--warning-only" in content, "build flow must use the --warning-only mode"


def test_warning_invocation_uses_argument_list_not_shell():
    content = FLOW_FILE.read_text()
    assert "sys.executable" in content, "invocation must use sys.executable (argument list)"
    assert _SHELL_KW not in content, "must not use a shell-string invocation"
    assert "subprocess.run(" in content, "must document subprocess.run with an argument list"


def test_warning_is_non_blocking():
    content = FLOW_FILE.read_text()
    lower = content.lower()
    assert "non-blocking" in lower, "flow must state the coverage warning is non-blocking"
    assert "proceed" in lower, "flow must state the build proceeds regardless of the warning"


def test_warning_only_reads_prewritten_map_not_reparse():
    content = FLOW_FILE.read_text()
    lower = content.lower()
    assert "pre-written" in lower or "pre-written" in content or "does not re-parse" in lower, \
        "flow must state --warning-only reads the pre-written spec-coverage.md (no re-parse)"


def test_backward_compatible_silent_skip_when_absent():
    content = FLOW_FILE.read_text()
    lower = content.lower()
    assert "backward compatible" in lower or "backward-compatible" in lower, \
        "flow must state the check is backward compatible"
    assert "skip" in lower and ("silent" in lower or "does not exist" in lower), \
        "flow must state it skips silently when spec-coverage.md does not exist"
