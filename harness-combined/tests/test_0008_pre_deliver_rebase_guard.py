"""
Content-verification tests for context/flows/deliver-ticket.md — Step 2b
(pre-deliver rebase guard). Verifies the flow file documents every behavior
required by spec 0008-pre-deliver-rebase-guard / requirements.md FR-1..FR-9.

These are prose-structure tests: the flow is executed by the model reading the
markdown, so the "implementation" is the documented procedure. Each test asserts
that a required instruction is present and correctly positioned.
"""
from pathlib import Path

FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "deliver-ticket.md"


def _content() -> str:
    return FLOW_FILE.read_text()


def _section(content: str, start_header: str, end_header: str | None = None) -> str:
    """Slice from start_header up to end_header (or EOF)."""
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


def test_flow_file_exists():
    assert FLOW_FILE.exists(), "context/flows/deliver-ticket.md must exist"


def test_step2b_positioned_between_step2_and_step3():
    content = _content()
    step2 = content.find("## Step 2 —")
    step2b = content.find("## Step 2b —")
    step3 = content.find("## Step 3 —")
    assert step2 >= 0 and step2b >= 0 and step3 >= 0, "Steps 2, 2b, 3 must all exist"
    assert step2 < step2b < step3, "Step 2b must sit between Step 2 and Step 3"


def test_step_numbering_after_2b_unchanged():
    # Inserting 2b must not renumber the downstream steps.
    content = _content()
    for header in ("## Step 3 —", "## Step 4 —", "## Step 5 —",
                   "## Step 6 —", "## Step 7 —", "## Step 8 —"):
        assert header in content, f"Downstream {header!r} must remain present and unrenumbered"


# --- FR-4: branch-name validation before any git command ---

def test_2b1_documents_validation_regex_and_prefire_halt():
    step2b = _section(_content(), "## Step 2b —", "## Step 3 —")
    assert r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*(/[a-zA-Z0-9][a-zA-Z0-9_.-]*)*$" in step2b, \
        "2b-1 must document the exact branch-name validation regex"
    assert "origin/main" in step2b, "regex rationale must note remote-tracking names are permitted"
    lower = step2b.lower()
    assert "before" in lower and "any git command" in lower, \
        "validation failure must halt before any git command runs (FR-4)"


# --- FR-1: divergence check command shape ---

def test_2b2_documents_rev_list_three_dot_positional():
    step2b = _section(_content(), "## Step 2b —", "## Step 3 —")
    assert "git rev-list --count" in step2b, "2b-2 must use git rev-list --count"
    assert '"$target_branch"..."$branch"' in step2b, \
        "2b-2 must use three-dot syntax with discrete quoted positional refs"
    assert "no network" in step2b.lower() or "local git state" in step2b.lower(), \
        "divergence check must be documented as local-only (NFR-1)"


# --- FR-2, FR-3: warning text + halt when behind without --rebase ---

def test_2b2_documents_exact_warning_and_halt():
    step2b = _section(_content(), "## Step 2b —", "## Step 3 —")
    assert ("Warning: branch is N commit(s) behind <target>. "
            "Pass --rebase to auto-rebase before delivering, or rebase manually.") in step2b, \
        "2b-2 must contain the exact FR-2 warning message"
    lower = step2b.lower()
    assert "halt delivery" in lower, "must halt delivery when behind and --rebase not passed (FR-3)"


# --- FR-8: proceed when up to date ---

def test_2b2_documents_up_to_date_proceed():
    step2b = _section(_content(), "## Step 2b —", "## Step 3 —")
    lower = step2b.lower()
    assert "n == 0" in lower or "n==0" in lower, "must handle the N == 0 case"
    assert "up to date" in lower and "proceed to step 3" in lower, \
        "N == 0 must mark 'up to date' and proceed to Step 3 (FR-8)"


# --- FR-5: mid-rebase guard ---

def test_2b3_documents_mid_rebase_guard():
    step2b = _section(_content(), "## Step 2b —", "## Step 3 —")
    lower = step2b.lower()
    assert "mid-rebase" in lower, "2b-3 must name the mid-rebase state"
    assert "halt" in lower and ("no rebase" in lower or "attempt no rebase" in lower), \
        "mid-rebase state must halt with a named error before any rebase (FR-5)"


def test_2b3_mid_rebase_guard_is_worktree_aware_not_failopen():
    # Regression guard for the post-build critic BLOCKER: the bare
    # "$worktree_path/.git/REBASE_HEAD" check can never fire for a linked
    # worktree (.git is a file), so the guard must resolve the real per-worktree
    # git dir via `rev-parse --git-path` and test the canonical rebase dirs.
    step2b = _section(_content(), "## Step 2b —", "## Step 3 —")
    assert "rev-parse --git-path" in step2b, \
        "2b-3 must resolve rebase state with `git rev-parse --git-path` (linked-worktree aware)"
    assert "rebase-merge" in step2b and "rebase-apply" in step2b, \
        "2b-3 must check the canonical rebase-merge / rebase-apply markers"
    assert '[[ -f "$worktree_path/.git/REBASE_HEAD" ]]' not in step2b, \
        "2b-3 must NOT use the fail-open bare .git/REBASE_HEAD path for a linked worktree"


# --- FR-7: conflict-abort path ---

def test_2b5_documents_conflict_abort_and_double_error():
    step2b = _section(_content(), "## Step 2b —", "## Step 3 —")
    assert "git -C \"$worktree_path\" rebase --abort" in step2b or "rebase --abort" in step2b, \
        "2b-5 must call git rebase --abort as a checked sub-step"
    lower = step2b.lower()
    assert "both" in lower, "abort failure must report BOTH errors (FR-7)"
    assert "do **not** proceed to step 3" in lower or "do not proceed to step 3" in lower, \
        "conflict cases must never proceed to Step 3 (FR-7)"


# --- FR-6: gate-invalidation notice on successful rebase ---

def test_2b6_documents_gate_invalidation_notice():
    step2b = _section(_content(), "## Step 2b —", "## Step 3 —")
    lower = step2b.lower()
    assert "gate-invalidation" in lower or "gates ran on the pre-rebase branch" in lower, \
        "2b-6 must define a gate-invalidation notice"
    assert "re-run" in lower and "/build" in step2b, \
        "gate-invalidation notice must advise re-running /build (FR-6)"


# --- FR-9: Step 3 surfaces the divergence result ---

def test_step3_surfaces_branch_status():
    step3 = _section(_content(), "## Step 3 —", "## Step 4 —")
    lower = step3.lower()
    assert "up to date" in lower and "rebased (was n behind)" in lower, \
        "Step 3 confirmation must surface the branch-status line (FR-9)"


def test_step3_includes_gate_invalidation_after_rebase():
    step3 = _section(_content(), "## Step 3 —", "## Step 4 —")
    assert "re-running /build" in step3 or "re-run /build" in step3 or "/build" in step3, \
        "Step 3 must carry the gate-invalidation notice after a successful rebase (FR-6/FR-9)"
