"""Content-verification tests for squash-merge ticket delivery (ticket 0003).

This ticket rewrites markdown instruction/reference files so that `main` keeps
only the claim commit and one squashed delivery commit per ticket; everything
between lives on the feature branch created at claim time. These tests assert the
key structural changes are present in each modified file. Mirrors
tests/test_ticket_archiving.py (ROOT + read(rel) helper).
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── FR-1: /deliver uses a squash merge (no --no-ff) ──────────────────────────
def test_deliver_uses_squash_merge() -> None:
    c = read("context/flows/deliver-ticket.md")
    assert "git merge --squash" in c
    assert "git merge --no-ff" not in c


# ── FR-2: done + archive folded into one commit, mirroring the archive pattern ─
def test_deliver_folds_done_and_archive_into_one_commit() -> None:
    c = read("context/flows/deliver-ticket.md")
    assert "deliver_squash" in c
    assert 'feat: XXXX <title> (squash)' in c
    assert "folded" in c.lower()
    # mirrors the archive pattern — OS mv + git rm --cached + git add (never git mv)
    assert "git rm -r --cached .tickets/XXXX-<slug>/" in c
    assert "git add -- .tickets/completed/XXXX-<slug>/" in c
    assert "never** `git mv`" in c  # the doc explicitly warns against git mv


# ── FR-3: branch + worktree created at claim (create-after-push) ──────────────
def test_problem_creates_branch_and_worktree_at_claim() -> None:
    c = read("commands/problem.md")
    assert "create-after-push" in c
    assert ".worktrees/XXXX-<slug>" in c
    assert "ticket/XXXX-<slug>" in c


def test_problem_writes_artifacts_in_worktree() -> None:
    c = read("commands/problem.md")
    assert "into the worktree" in c.lower()


# ── FR-4: the claim commit is the only main commit before delivery ───────────
def test_problem_claim_is_only_main_commit_pre_delivery() -> None:
    c = read("commands/problem.md")
    assert "only" in c and "before delivery" in c


def test_reference_documents_two_commits_on_main() -> None:
    c = read("context/harness-reference.md")
    assert "squashed delivery commit" in c
    assert "`claimed`" in c


# ── FR-5: post-claim states are branch-only; no design commit on main ────────
def test_reference_states_are_branch_only() -> None:
    c = read("context/harness-reference.md")
    assert "branch only" in c.lower()
    # the four post-claim implementation states are named as branch-only
    assert "`solution`, `implementing`, `review-ready`, `changes-requested`" in c


def test_reference_drops_implementing_to_main_causal_note() -> None:
    c = read("context/harness-reference.md")
    # the old "build commits implementing to main and pushes before forking" chain is gone
    assert "commits `implementing` to `main` and pushes" not in c


def test_problem_design_commit_is_on_branch_not_main() -> None:
    c = read("commands/problem.md")
    assert 'git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX design' in c
    # the bare (main) design commit must be gone
    assert 'git commit -m "chore(ticket): XXXX design' not in c


def test_build_implementing_branch_only() -> None:
    c = read("context/flows/build-ticket.md")
    assert "set-status XXXX implementing --push" in c
    assert "branch only" in c.lower()


# ── FR-6: /reopen forks a fresh branch from main HEAD ────────────────────────
def test_reopen_forks_fresh_branch_from_main() -> None:
    c = read("commands/reopen.md")
    assert "git worktree add .worktrees/XXXX-<slug> -b ticket/XXXX-<slug> main" in c
    assert "fresh branch" in c.lower()


def test_reopen_restores_onto_branch() -> None:
    c = read("commands/reopen.md")
    assert "git -C .worktrees/XXXX-<slug> rm -r --cached .tickets/completed/XXXX-<slug>/" in c


# ── FR-7: /cancel and /abandon remove worktree+branch, route via set-status ──
def test_cancel_routes_terminal_via_set_status() -> None:
    c = read("commands/cancel.md")
    assert "set-status XXXX cancelled --push" in c
    assert "claim time" in c  # worktree+branch exist from claim


def test_abandon_routes_terminal_via_set_status() -> None:
    c = read("commands/abandon.md")
    assert "set-status XXXX abandoned --push" in c
    assert "claim time" in c


# ── FR-8: the commit guard scans worktrees (documented in the reference) ─────
def test_reference_documents_guard_worktree_discovery() -> None:
    c = read("context/harness-reference.md")
    assert "git worktree list" in c
    assert "git rev-parse --git-common-dir" in c


# ── FR-9: status-reading skills read the worktree status.md when present ──────
def test_status_skill_reads_worktree() -> None:
    c = read("skills/status/SKILL.md")
    assert ".worktrees/<slug>/" in c
    assert "limitation" in c.lower()


def test_ticket_status_reads_worktree() -> None:
    c = read("commands/ticket-status.md")
    assert ".worktrees/<slug>/" in c
    assert "limitation" in c.lower()


def test_suggest_skill_reads_worktree() -> None:
    c = read("skills/suggest/SKILL.md")
    assert ".worktrees/<slug>/" in c
    assert "limitation" in c.lower()
