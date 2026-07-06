"""
Content-verification tests for commands/replan.md
Verifies the /replan command spec documents all required behaviors per
requirements 0033 (FR-1..FR-10, NFR-1, NFR-2) and the LLM-observability constraint.

These are structural substring checks: the deliverable is a Markdown command spec,
so the "behavior" under test is the documented procedure, mirroring the
test_0038_stack_advisor_flow.py convention.
"""
from pathlib import Path

CMD_FILE = Path(__file__).parent.parent / "commands" / "replan.md"


def _content() -> str:
    return CMD_FILE.read_text()


def _section_from(content: str, start_header: str, end_header: str | None = None) -> str:
    """Extract a section from start_header to end_header (or end of file if None)."""
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


def test_command_file_exists():
    assert CMD_FILE.exists(), "commands/replan.md must exist"


# --- FR-1: ticket resolution ---

def test_documents_ticket_resolution_lookup_order():
    c = _content()
    assert ".tickets/<arg>*/" in c or ".tickets/<arg>" in c, \
        "Must document scanning .tickets/<arg>*/ for resolution (FR-1)"
    assert ".tickets/completed/" in c, \
        "Must document the .tickets/completed/ fallback lookup (FR-1)"


def test_documents_ambiguous_input_lists_candidates():
    c = _content().lower()
    assert "ambiguous" in c or "multiple" in c or "list" in c, \
        "Must document that ambiguous/empty input lists candidates (FR-1)"


# --- FR-2: status guard ---

def test_status_guard_accepts_valid_statuses():
    c = _content()
    for status in ["solution", "implementing", "review-ready", "changes-requested"]:
        assert status in c, f"Status guard must document accepting '{status}' (FR-2)"


def test_status_guard_rejects_requirements_and_problem():
    c = _content().lower()
    assert "requirements" in c and "problem" in c, \
        "Status guard must document rejecting the requirements and problem statuses (FR-2)"
    assert "reject" in c or "excluded" in c or "not one of" in c, \
        "Status guard must document rejection behavior (FR-2)"


# --- FR-3: read artifacts before regeneration ---

def test_reads_problem_and_requirements_before_regeneration():
    c = _content()
    assert "problem.md" in c and "requirements.md" in c, \
        "Must document reading problem.md and requirements.md (FR-3)"
    lower = c.lower()
    assert "in full" in lower or "read" in lower, \
        "Must document reading the artifacts before regeneration (FR-3)"


# --- FR-4 / NFR-2: snapshot ---

def test_documents_git_show_snapshot():
    c = _content()
    assert "git show HEAD:" in c, \
        "Must document snapshotting solution.md via `git show HEAD:<path>` (FR-4)"


def test_documents_empty_snapshot_fallback():
    c = _content().lower()
    assert "empty" in c and ("fallback" in c or "no prior" in c or "does not exist" in c
                             or "never committed" in c or "no existing" in c), \
        "Must document an empty-snapshot fallback for the no-prior-commit case (NFR-2)"


# --- FR-5: regeneration mirrors /problem Phase 4 ---

def test_documents_regeneration_mirrors_problem_phase_4():
    c = _content()
    assert "Phase 4" in c, \
        "Must document regenerating solution.md mirroring /problem Phase 4 (FR-5)"


def test_documents_fail_closed_write():
    c = _content().lower()
    assert "fail-closed" in c or "fail closed" in c, \
        "Must document a fail-closed regeneration write"
    assert "abort" in c or "do not" in c or "never" in c, \
        "Must document aborting before overwriting on empty/invalid regeneration"


# --- LLM observability constraint ---

def test_documents_llm_observability():
    c = _content().lower()
    assert "observability" in c or ("log" in c and "prompt" in c), \
        "Must document logging the regeneration LLM invocation (observability)"
    # prompt, response, and tool calls must all be named
    assert "prompt" in c, "Observability must name the rendered prompt"
    assert "response" in c or "output" in c, "Observability must name the model response/output"
    assert "tool call" in c or "tool-call" in c, "Observability must name tool calls"


# --- FR-6: critic loop, 2-round cap ---

def test_documents_critic_loop_two_round_cap():
    c = _content()
    assert "critic" in c.lower(), "Must document the critic loop (FR-6)"
    assert "2 round" in c.lower() or "2-round" in c.lower() or "max 2" in c.lower() \
        or "two round" in c.lower() or "Round: **2**" in c or "rounds 1" in c.lower(), \
        "Must document an explicit 2-round cap (FR-6)"


def test_critic_cap_stated_inline_not_delegated():
    c = _content().lower()
    # The cap must be explicit in this file (per solution.md tradeoff), not only "same as /problem"
    assert "cap" in c or "maximum" in c or "max 2" in c or "at most" in c, \
        "The 2-round cap must be explicitly stated inline in replan.md (FR-6)"


# --- FR-7: diff ---

def test_documents_git_diff_no_index_with_exit_handling():
    c = _content()
    assert "git diff --no-index" in c, \
        "Must document the unified diff via `git diff --no-index` (FR-7)"
    assert "|| true" in c, \
        "Must document explicit `|| true` exit-code handling for git diff --no-index (FR-7)"


def test_documents_no_changes_notice():
    c = _content().lower()
    assert "no changes" in c, \
        "Must document a 'no changes' notice when old and new content are identical (FR-7)"


# --- FR-8: status update ---

def test_documents_status_update_to_solution_with_date():
    c = _content()
    assert "status: solution" in c, "Must document updating status.md to status: solution (FR-8)"
    lower = c.lower()
    assert "date" in lower or "updated" in lower, \
        "Must document updating the updated date (FR-8)"


# --- FR-9: commit ---

def test_documents_single_commit_message_convention():
    c = _content()
    assert "chore(ticket): XXXX replan (status: solution)" in c, \
        "Must document the exact commit message convention (FR-9)"


def test_documents_commit_targets_main_and_three_files():
    c = _content()
    assert "solution.md" in c and "status.md" in c and "requirements.md" in c, \
        "Must document committing solution.md, status.md, and requirements.md (FR-9)"
    assert "main" in c, "Must document committing to main (FR-9)"


def test_documents_rollback_aware_commit_message():
    c = _content().lower()
    assert "rollback" in c, \
        "Must document a rollback-aware commit message encoding the prior status (FR-9)"


# --- FR-10: worktree guard ---

def test_documents_worktree_detection():
    c = _content()
    assert "git worktree list" in c, \
        "Must document detecting the worktree via `git worktree list` (FR-10)"


def test_documents_checkpoint_style_prompt():
    c = _content()
    assert "Proceed? (yes/no)" in c or "(yes/no)" in c, \
        "Must present a Checkpoint-style (yes/no) prompt, not a bare stdin read (FR-10)"
    lower = c.lower()
    assert "explicit" in lower and "yes" in lower, \
        "Must require an explicit yes before proceeding (FR-10)"


def test_documents_worktree_divergence_warning():
    c = _content().lower()
    assert "diverge" in c or "divergence" in c or "reconcile" in c, \
        "Worktree guard must warn about implementation divergence / reconciliation (FR-10)"
    assert "git worktree remove" in _content() or "re-run" in c or "rebuild" in c, \
        "Worktree guard should name the reconciliation path (remove worktree / re-run /build)"


# --- NFR-1: idempotency / structural contract ---

def test_documents_structural_contract_for_regeneration():
    c = _content()
    # The regenerated solution must follow the standard section structure (idempotent contract)
    assert "Approach" in c or "Components" in c or "Implementation Order" in c, \
        "Regeneration must document the standard solution.md section structure (NFR-1)"
