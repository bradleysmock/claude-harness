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
    # ticket 0068 moved the raw git sequence behind ticket.py's deliver-commit CLI;
    # the doc now documents the call, not the inlined git rm/add pair.
    assert "deliver-commit" in c
    assert "deliver_commit()" in c
    assert 'feat: XXXX <title> (squash)' in c
    assert "folded" in c.lower()
    # mirrors the archive pattern — OS mv + git rm --cached + git add (never git mv)
    assert "git rm -r --cached" in c
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


# ── FR-4: the claim makes NO main commit — the ledger is the arbiter ─────────
# NEW CONTRACT: was "the claim commit is the only main commit before delivery".
# Number allocation moved to the harness-tickets ledger, so the claim writes
# nothing to main; the delivery squash is the ONLY main commit per ticket.
def test_problem_claim_makes_no_main_commit() -> None:
    c = read("commands/problem.md")
    assert "nothing to `main`" in c
    assert "harness-tickets" in c and "ledger" in c


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
    # NEW CONTRACT: reopen delegates to the helper, which restores the dir onto the
    # fresh branch from its archive (main's completed/ or harness-tickets). Old
    # assertion pinned the hand-rolled `git -C .worktrees/... rm -r --cached
    # .tickets/completed/...` command.
    c = read("commands/reopen.md")
    assert 'ticket.py" reopen XXXX --push' in c
    assert "restore" in c.lower() and "archive" in c.lower()


# ── FR-7: /cancel and /abandon are main-free, routed via the ledger helper ───
# NEW CONTRACT: terminal handling moved off `main`. Cancel/abandon append a
# `cancelled`/`abandoned` ledger event and archive docs onto harness-tickets via
# the helper (`ticket.py cancel|abandon`), instead of a main-side set-status +
# completed/ archive commit.
def test_cancel_routes_terminal_via_ledger_helper() -> None:
    c = read("commands/cancel.md")
    assert 'ticket.py" cancel XXXX --push' in c
    assert "main-free" in c


def test_abandon_routes_terminal_via_ledger_helper() -> None:
    c = read("commands/abandon.md")
    assert 'ticket.py" abandon XXXX --push' in c
    assert "main-free" in c


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
