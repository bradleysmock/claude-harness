"""
Content-verification tests for commands/problem.md Phase 6 (Spec Score Check).
Verifies Phase 6 actually runs the score-spec check and that the Checkpoint 1
template carries the verdict, per spec 0045-problem-phase6-score-spec.
"""
from pathlib import Path

PROBLEM_FILE = Path(__file__).parent.parent / "commands" / "problem.md"


def _section(content: str, start_header: str, end_header: str | None = None) -> str:
    """Extract a section from start_header to end_header (or end of file)."""
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


def _phase6(content: str) -> str:
    return _section(content, "## Phase 6", "## Checkpoint 1 — Present to Lead")


def _checkpoint1(content: str) -> str:
    return _section(content, "## Checkpoint 1: Ready to implement?")


def test_problem_file_exists():
    assert PROBLEM_FILE.exists(), "commands/problem.md must exist"


# FR-1: Phase 6 reads score-spec.md and applies its checks to the artifacts, showing the report.

def test_phase6_names_score_spec_md():
    phase6 = _phase6(PROBLEM_FILE.read_text())
    assert "score-spec.md" in phase6, \
        "Phase 6 must name context/score-spec.md"


def test_phase6_instructs_reading_in_full_and_applying():
    phase6 = _phase6(PROBLEM_FILE.read_text()).lower()
    assert "in full" in phase6, "Phase 6 must instruct reading score-spec.md in full"
    assert "apply" in phase6, "Phase 6 must instruct applying score-spec's checks"


def test_phase6_applies_to_requirements_and_solution():
    phase6 = _phase6(PROBLEM_FILE.read_text())
    assert "requirements.md" in phase6, "Phase 6 must apply checks to requirements.md"
    assert "solution.md" in phase6, "Phase 6 must apply checks to solution.md"


def test_phase6_displays_per_check_report():
    phase6 = _phase6(PROBLEM_FILE.read_text()).lower()
    # Anchor on the display instruction itself, not the ubiquitous word "verdict"
    # (which appears in headings and prose throughout Phase 6).
    assert "per-check report" in phase6, \
        "Phase 6 must instruct displaying the structured per-check report"
    assert "verbatim" in phase6, \
        "Phase 6 must instruct displaying the report verbatim"


# FR-2: two-pass fix budget and residual-BLOCK reporting.

def test_phase6_documents_two_pass_budget():
    phase6 = _phase6(PROBLEM_FILE.read_text()).lower()
    # "pass"/"PASS" and "two" appear via the verbatim [PASS|WARN|BLOCK] report line,
    # so anchor on the specific budget phrasing instead.
    assert "two fix passes" in phase6 or "two-pass" in phase6 or "at most two passes" in phase6, \
        "Phase 6 must document the at-most-two-pass fix budget"


def test_phase6_documents_block_revise_and_rescore():
    phase6 = _phase6(PROBLEM_FILE.read_text()).lower()
    # "block" alone is satisfied by the verbatim [PASS|WARN|BLOCK] report line;
    # anchor on the BLOCK-handling branch prose.
    assert "if the verdict is" in phase6, \
        "Phase 6 must branch on the BLOCK verdict (revise + re-score)"
    assert "re-score" in phase6 or "re-apply" in phase6 or "rescore" in phase6, \
        "Phase 6 must instruct re-scoring after a fix pass"


def test_phase6_documents_residual_block_in_checkpoint():
    phase6 = _phase6(PROBLEM_FILE.read_text()).lower()
    assert "residual block" in phase6, \
        "Phase 6 must document carrying a residual BLOCK into the Checkpoint 1 summary"
    assert "hide" in phase6 or "hidden" in phase6, \
        "Phase 6 must state a residual BLOCK is not hidden"


# NFR-2: no subagent spawned in Phase 6.

def test_phase6_states_no_subagent():
    phase6 = _phase6(PROBLEM_FILE.read_text()).lower()
    assert "subagent" in phase6, \
        "Phase 6 must state no subagent is spawned (reuses design-session context)"


# FR-4: fix-pass revisions committed on the branch per Phase 5 convention.

def test_phase6_commits_fixes_on_branch():
    phase6 = _phase6(PROBLEM_FILE.read_text())
    lower = phase6.lower()
    assert "branch" in lower, "Phase 6 must document committing fix-pass revisions on the branch"
    assert "chore(ticket): XXXX design (status: solution)" in phase6, \
        "Phase 6 must reuse the Phase 5 design commit convention"


# FR-3: Checkpoint 1 template carries the score-spec verdict line.

def test_checkpoint1_has_score_spec_verdict_line():
    checkpoint = _checkpoint1(PROBLEM_FILE.read_text())
    lower = checkpoint.lower()
    assert "score-spec" in lower, \
        "Checkpoint 1 template must include a score-spec verdict line"
    assert "PASS" in checkpoint and "WARN" in checkpoint and "BLOCK" in checkpoint, \
        "Checkpoint 1 verdict line must name the PASS / WARN / BLOCK outcomes with named checks"
