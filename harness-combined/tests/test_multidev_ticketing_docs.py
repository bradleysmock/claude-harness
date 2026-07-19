from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── Task 5: problem.md claim phase ──────────────────────────────
def test_problem_claim_uses_helper() -> None:
    c = read("commands/problem.md")
    assert "ticket claim" in c or "ticket.py claim" in c


def test_problem_claim_sets_claimed_status() -> None:
    assert "status: claimed" in read("commands/problem.md")


def test_problem_records_owner() -> None:
    assert "owner:" in read("commands/problem.md")


def test_problem_no_longer_references_next_ticket() -> None:
    assert "NEXT_TICKET" not in read("commands/problem.md")


def test_problem_claim_pushes() -> None:
    c = read("commands/problem.md")
    assert "git push" in c or "--push" in c


# ── Task 6: build-ticket.md resumes the claim worktree, branch-only churn ────
# (Ticket 0003: the worktree is created at claim time, so /build resumes it and
#  `implementing` is branch-only — it is no longer committed to main before a fork.)
def test_build_resumes_claim_worktree_not_creates() -> None:
    c = read("context/flows/build-ticket.md").lower()
    assert "do not create" in c or "resume" in c
    assert "already exist" in c


def test_build_implementing_is_branch_only_and_pushed() -> None:
    c = read("context/flows/build-ticket.md")
    assert "branch only" in c.lower()
    # implementing is committed + pushed on the branch via the helper, never to main
    assert "set-status XXXX implementing --push" in c


def test_build_review_ready_commits_on_branch() -> None:
    c = read("context/flows/build-ticket.md")
    assert "branch only" in c or "on the branch" in c
    # review-ready commit must run inside the worktree, not against main
    assert "git -C .worktrees/XXXX-<slug>" in c or "in the worktree" in c


# ── Task 7: deliver-ticket.md — squash merge, folded done+archive ────────────
def test_deliver_uses_squash_merge() -> None:
    c = read("context/flows/deliver-ticket.md")
    assert "git merge --squash" in c
    assert "git merge --no-ff" not in c  # the old --no-ff path is gone


def test_deliver_documents_squash_status_resolution() -> None:
    c = read("context/flows/deliver-ticket.md").lower()
    assert "squash" in c
    assert "no conflict" in c or "cleanly" in c


# ── Task 8: /abandon command + /cancel --abandon alias ──────────────────────
def test_abandon_command_exists() -> None:
    assert (ROOT / "commands/abandon.md").exists()


def test_abandon_sets_abandoned_status() -> None:
    # NEW CONTRACT: the terminal signal is an `abandoned` event on the
    # harness-tickets ledger (main-free), not a `status: abandoned` commit on main.
    c = read("commands/abandon.md")
    assert "abandoned" in c
    assert 'ticket.py" abandon XXXX --push' in c


def test_abandon_distinct_from_cancelled() -> None:
    c = read("commands/abandon.md")
    assert "started but dropped" in c or "dropped" in c


def test_cancel_supports_abandon_alias() -> None:
    c = read("commands/cancel.md")
    assert "--abandon" in c
    assert "abandoned" in c


# ── Task 9: /status owner column + stale-implementing flag ──────────────────
def test_status_skill_shows_owner() -> None:
    assert "owner" in read("skills/status/SKILL.md").lower()


def test_status_skill_flags_stale_implementing() -> None:
    c = read("skills/status/SKILL.md").lower()
    assert "stale" in c and "implementing" in c


def test_ticket_status_shows_owner() -> None:
    assert "owner" in read("commands/ticket-status.md").lower()


# ── Task 10: harness-reference.md lifecycle, state-split, NEXT_TICKET, GitHub seam ──
def test_reference_has_claimed_and_abandoned() -> None:
    c = read("context/harness-reference.md")
    assert "`claimed`" in c and "`abandoned`" in c


def test_reference_removes_next_ticket_counter() -> None:
    c = read("context/harness-reference.md")
    # The directory-listing line that documented NEXT_TICKET must be gone.
    assert "NEXT_TICKET        # Next available" not in c
    assert "max(existing" in c or "scans both" in c.lower() or "active and completed" in c.lower()


def test_reference_documents_state_split() -> None:
    c = read("context/harness-reference.md").lower()
    assert "branch only" in c or "branch-local" in c


def test_reference_documents_github_seam_fields() -> None:
    c = read("context/harness-reference.md")
    assert "source:" in c and "external_id:" in c


def test_reference_documents_owner_field() -> None:
    assert "owner:" in read("context/harness-reference.md")
