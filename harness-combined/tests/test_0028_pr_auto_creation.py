"""
Content-verification tests for ticket 0028 — GitHub PR auto-creation.

Verifies that `commands/deliver.md` and `context/flows/deliver-ticket.md` document
every behavior required by 0028's requirements.md (FR-1 … FR-14 + FR-14a, mktemp).
These flow files are executed by the model, so the "implementation" is prose + the
embedded `gh_guard` / `pr_body_builder` named shell blocks; the tests assert the
structural substrings that encode each requirement.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
DELIVER_CMD = ROOT / "commands" / "deliver.md"
DELIVER_TICKET = ROOT / "context" / "flows" / "deliver-ticket.md"


def _cmd() -> str:
    return DELIVER_CMD.read_text()


def _flow() -> str:
    return DELIVER_TICKET.read_text()


def _section(content: str, start: str, end: str | None = None) -> str:
    i = content.find(start)
    assert i >= 0, f"Section '{start}' not found"
    if end is None:
        return content[i:]
    j = content.find(end, i + len(start))
    return content[i:j] if j >= 0 else content[i:]


# --- files exist ---

def test_files_exist():
    assert DELIVER_CMD.exists(), "commands/deliver.md must exist"
    assert DELIVER_TICKET.exists(), "context/flows/deliver-ticket.md must exist"


# --- FR-14 + deliver.md forwarding: spec-mode --pr warning ---

def test_deliver_cmd_forwards_pr_to_ticket_mode():
    """FR-1/FR-11: --pr recognized and forwarded in ticket mode."""
    c = _cmd()
    assert "--pr" in c, "deliver.md must mention the --pr flag"


def test_deliver_cmd_warns_pr_in_spec_mode():
    """FR-14: --pr in spec mode → warning, spec deliver proceeds."""
    c = _cmd()
    lower = c.lower()
    assert "--pr" in c and "spec mode" in lower, \
        "deliver.md must document --pr handling in spec mode"
    assert "only supported in ticket mode" in lower or "ticket mode only" in lower, \
        "deliver.md must warn that --pr is only supported in ticket mode"
    assert "continue" in lower or "proceed" in lower, \
        "deliver.md must state the spec deliver flow continues after the warning"


# --- named blocks exist (solution.md Components) ---

def test_gh_guard_named_block_present():
    f = _flow()
    assert "gh_guard" in f, "deliver-ticket.md must define the gh_guard named block"


def test_pr_body_builder_named_block_present():
    f = _flow()
    assert "pr_body_builder" in f, \
        "deliver-ticket.md must define the pr_body_builder named block"


# --- FR-1: --pr accepted in ticket mode ---

def test_flow_documents_pr_flag():
    f = _flow()
    assert "--pr" in f, "deliver-ticket.md must document the --pr flag"


# --- FR-2 / FR-11: push before PR, PR before local merge ---

def test_push_and_pr_occur_before_merge():
    """FR-2/FR-11: the PR step (3.5) must appear before the squash-merge (Step 4)."""
    f = _flow()
    pr_step = f.find("Step 3.5")
    merge_step = f.find("## Step 4 —")
    assert pr_step >= 0, "deliver-ticket.md must add a Step 3.5 for push + PR creation"
    assert merge_step >= 0, "Step 4 (squash-merge) must exist"
    assert pr_step < merge_step, "PR creation (Step 3.5) must occur before the local merge (Step 4)"


def test_push_precedes_pr_create_within_step():
    """FR-2: branch is pushed before gh pr create."""
    f = _flow()
    step = _section(f, "## Step 3.5", "## Step 4 —")
    push_pos = step.find("git push")
    create_pos = step.find("gh pr create")
    assert push_pos >= 0, "Step 3.5 must push the branch"
    assert create_pos >= 0, "Step 3.5 must call gh pr create"
    assert push_pos < create_pos, "the branch must be pushed before gh pr create"


# --- FR-3: shell-quoted title, no concatenation ---

def test_title_is_double_quoted_no_concatenation():
    """FR-3: title passed as a double-quoted variable, never string-concatenated."""
    f = _flow()
    assert '"$TICKET_TITLE"' in f or '"${TICKET_TITLE}"' in f, \
        "the PR title must be passed as a double-quoted shell variable (no concatenation)"


# --- FR-4: Approach extraction + placeholder ---

def test_approach_awk_extraction_no_end_block():
    """FR-4: awk extracts ## Approach; the tradeoff prohibits an END block."""
    # end at "## Step" (not "## ") — the awk pattern itself contains "## Approach"
    builder = _section(_flow(), "pr_body_builder", "## Step")
    # awk extraction keyed on the Approach header
    assert "Approach" in builder, "pr_body_builder must extract the ## Approach section"
    assert "awk" in builder, "pr_body_builder must use awk to extract Approach"
    # No END block (awk `exit` skips END in some impls — solution.md tradeoff)
    assert "END{" not in builder and "END {" not in builder, \
        "pr_body_builder awk must not use an END block (see solution.md tradeoff)"


def test_approach_absent_placeholder():
    """FR-4: absent/empty Approach → explicit placeholder, no error."""
    f = _flow()
    assert "(No Approach section found in solution.md)" in f, \
        "pr_body_builder must use the literal Approach placeholder when the section is absent"


# --- FR-5: AC checklist + placeholder ---

def test_acceptance_criteria_rendered_as_checklist():
    """FR-5: Acceptance Criteria rendered as `- [ ]` checkbox items."""
    builder = _section(_flow(), "pr_body_builder", "## Step")
    assert "- [ ]" in builder, \
        "pr_body_builder must render Acceptance Criteria as a `- [ ]` checklist"
    assert "Acceptance Criteria" in builder, \
        "pr_body_builder must read the Acceptance Criteria section"


def test_acceptance_criteria_first_line_only():
    """FR-5: multi-line AC item → first non-blank line only."""
    builder = _section(_flow(), "pr_body_builder", "## Step")
    lower = builder.lower()
    assert "first" in lower and "line" in lower, \
        "pr_body_builder must document taking the first non-blank line per AC item"


def test_acceptance_criteria_absent_placeholder():
    """FR-5: absent/empty AC → placeholder, no error."""
    builder = _section(_flow(), "pr_body_builder", "## Step")
    # T3: bind the exact placeholder literal, not just the word "placeholder"
    assert "(No Acceptance Criteria section found in requirements.md)" in builder, \
        "pr_body_builder must use the literal AC placeholder when the section is absent"


# --- FR-6: ticket reference ---

def test_body_includes_ticket_reference():
    """FR-6: body includes a `Ticket:` reference."""
    builder = _section(_flow(), "pr_body_builder", "## Step")
    assert "Ticket:" in builder, \
        "pr_body_builder must append a `Ticket: <n>` reference to the PR body"


# --- mktemp + trap ---

def test_mktemp_and_trap_cleanup():
    """mktemp body file with trap-based cleanup; abort before push on failure."""
    builder = _section(_flow(), "pr_body_builder", "## Step")
    assert "mktemp" in builder, "pr_body_builder must use mktemp for the body file"
    assert "trap" in builder and "EXIT" in builder, \
        "pr_body_builder must register a trap ... EXIT cleanup for the temp file"


def test_mktemp_failure_aborts_before_push():
    """mktemp failure → abort before the branch is pushed."""
    f = _flow()
    builder = _section(f, "pr_body_builder", "## Step")
    lower = builder.lower()
    assert "abort" in lower or "exit" in lower, \
        "pr_body_builder must abort when mktemp fails"


# --- gh exit-code classification (FR-7, FR-8, FR-9, FR-13, FR-14a) ---

def test_gh_not_installed_skips_with_warning():
    """FR-7: command -v gh non-zero → skip + warn + continue."""
    guard = _section(_flow(), "gh_guard", "## ")
    assert "command -v gh" in guard, \
        "gh_guard must detect a missing gh via `command -v gh`"
    lower = guard.lower()
    assert "skip" in lower and ("warn" in lower or "warning" in lower), \
        "gh_guard must skip with a warning when gh is not installed"


def test_gh_not_authenticated_skips_with_warning():
    """FR-8: gh auth status non-zero → skip + warn + continue."""
    guard = _section(_flow(), "gh_guard", "## ")
    assert "gh auth status" in guard, \
        "gh_guard must check authentication via `gh auth status`"
    # T2: the auth case must explicitly skip + warn + continue, not merely mention the command
    auth_line = next((ln for ln in guard.splitlines()
                      if "gh auth status" in ln and "Not authenticated" in ln), "")
    lower = auth_line.lower()
    assert "skip" in lower and ("warn" in lower or "warning" in lower) and "continue" in lower, \
        "the Not-authenticated case must skip + warn + continue"


def test_existing_open_pr_detected_by_state():
    """FR-13: existing OPEN PR detected by state; MERGED/CLOSED not treated as open."""
    guard = _section(_flow(), "gh_guard", "## ")
    assert "gh pr view" in guard, "gh_guard must pre-check for an existing PR via gh pr view"
    assert "--json state" in guard and ".state" in guard, \
        "gh_guard must read the PR state via --json state --jq '.state'"
    assert '"OPEN"' in guard, \
        "gh_guard must compare state to the literal \"OPEN\" (closed/merged must not block)"


def test_existing_open_pr_prints_url_and_continues():
    """FR-13: on existing OPEN PR, print the URL, skip create, continue to merge."""
    guard = _section(_flow(), "gh_guard", "## ")
    lower = guard.lower()
    assert "url" in lower, "gh_guard must print the existing PR URL"
    assert "skip" in lower or "continue" in lower, \
        "gh_guard must skip creation and continue on an existing open PR"


def test_toctou_duplicate_treated_as_existing():
    """FR-14a: gh pr create dup stderr → fetch URL, continue (not hard stop)."""
    guard = _section(_flow(), "gh_guard", "## ")
    lower = guard.lower()
    assert "already exists" in lower or "already has" in lower, \
        "gh_guard must catch the duplicate-PR stderr pattern (TOCTOU)"
    # T1: the dup path must CONTINUE to merge, not hard-stop — bind the distinguishing behavior.
    dup_line = next((ln for ln in guard.splitlines()
                     if ("already exists" in ln or "already has" in ln)), "").lower()
    assert "not" in dup_line and ("hard stop" in dup_line or "stop" in dup_line) \
        or "continue" in dup_line, \
        "the TOCTOU duplicate case must continue to the merge (explicitly NOT a hard stop)"


def test_unexpected_failure_stops_with_recovery():
    """FR-9: non-dup gh pr create failure → stop + recovery instructions."""
    guard = _section(_flow(), "gh_guard", "## ")
    lower = guard.lower()
    assert "stop" in lower, "gh_guard must stop on an unexpected gh pr create failure"
    assert "recover" in lower or "already pushed" in lower or "recovery" in lower, \
        "gh_guard must print recovery instructions (branch already pushed) on hard stop"


def test_classification_distinguishes_push_from_create_failure():
    """Risk mitigation: error message distinguishes push failure from PR-create failure."""
    f = _flow()
    step = _section(f, "## Step 3.5", "## Step 4 —")
    # T5: bind both distinct failure-mode labels, not just the words "push"/"pr"
    assert "push failure" in step, \
        "Step 3.5 must label a failed push as a 'push failure'"
    assert "PR-creation failure" in step or "PR-create failure" in step, \
        "Step 3.5 must label a failed gh pr create distinctly as a 'PR-creation failure'"


# --- FR-12: confirm prompt lists push + gh pr create when --pr ---

def test_confirm_prompt_lists_push_and_pr_when_pr_flag():
    """FR-12: Step 3 confirm prompt includes push + gh pr create when --pr is active."""
    step3 = _section(_flow(), "## Step 3 — Confirm", "## Step 3.5")
    if step3 == _flow()[_flow().find("## Step 3 — Confirm"):]:
        step3 = _section(_flow(), "## Step 3 — Confirm", "## Step 4 —")
    assert "git push origin" in step3, \
        "Step 3 confirm prompt must list `git push origin <branch>` when --pr is present"
    assert "gh pr create" in step3, \
        "Step 3 confirm prompt must list `gh pr create` when --pr is present"


# --- FR-10: no --pr → unchanged ---

def test_no_pr_flag_unchanged_behavior_documented():
    """FR-10: when --pr is absent, deliver behavior is unchanged."""
    f = _flow()
    lower = f.lower()
    assert "when `--pr` is not passed" in lower or "without `--pr`" in lower \
        or "no `--pr`" in lower or "absent" in lower, \
        "deliver-ticket.md must state that behavior is unchanged when --pr is absent"


# --- NFR-1: gh detection bounded (documented) ---

def test_gh_detection_is_single_attempt_no_retry():
    """NFR-2: PR creation is one attempt, no retry."""
    guard = _section(_flow(), "gh_guard", "## ")
    lower = guard.lower()
    assert "one attempt" in lower or "no retry" in lower or "single attempt" in lower \
        or "not retry" in lower, \
        "gh_guard must state PR creation is a single attempt (no retry)"


# --- M3 / T4: NFR-1 5-second bound is enforced by a mechanism, not just asserted ---

def test_gh_probes_bounded_by_timeout():
    """NFR-1: the auth + existing-PR probes are wrapped in `timeout 5` (enforced, not asserted)."""
    guard = _section(_flow(), "gh_guard", "## ")
    assert "timeout 5 gh auth status" in guard, \
        "gh_guard must bound `gh auth status` with `timeout 5` (NFR-1 mechanism)"
    assert "timeout 5 gh pr view" in guard, \
        "gh_guard must bound the existing-PR probe `gh pr view` with `timeout 5` (NFR-1 mechanism)"


# --- M1: the PR title is actually sourced (not an unbound variable) ---

def test_ticket_title_is_sourced():
    """FR-3: TICKET_TITLE must be explicitly read from status.md/problem.md before use."""
    step = _section(_flow(), "## Step 3.5", "## Step 4 —")
    lower = step.lower()
    assert "title:" in step or "**title**" in lower, \
        "Step 3.5 must extract the PR title from status.md's title: field or problem.md's **Title** line"
    assert "status.md" in step and "problem.md" in step, \
        "Step 3.5 must name the source(s) the title is read from"


# --- M2: builder temp file survives until gh pr create (same-shell lifetime) ---

def test_body_file_same_shell_lifetime_documented():
    """M2: the EXIT-trap temp file must survive until gh pr create — same shell, no subshell."""
    builder = _section(_flow(), "pr_body_builder", "## Step")
    lower = builder.lower()
    assert "same shell" in lower, \
        "pr_body_builder must state builder + gh pr create run in the same shell session"
    assert "command substitution" in lower or "subshell" in lower, \
        "pr_body_builder must warn against running the builder in a subshell/command substitution"
