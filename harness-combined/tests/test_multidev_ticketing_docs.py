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


# ── Task 6: build-ticket.md implementing ordering + branch-local churn ──────
def test_build_sets_implementing_before_worktree() -> None:
    c = read("context/flows/build-ticket.md")
    impl = c.index("status: implementing")
    wt = c.index("git worktree add")
    assert impl < wt, "implementing must be committed to main before the worktree is forked"


def test_build_pushes_start_signal() -> None:
    c = read("context/flows/build-ticket.md")
    seg = c[c.index("status: implementing"):c.index("git worktree add")]
    assert "git push" in seg


def test_build_review_ready_commits_on_branch() -> None:
    c = read("context/flows/build-ticket.md")
    assert "branch only" in c or "on the branch" in c
    # review-ready commit must run inside the worktree, not against main
    assert "git -C .worktrees/XXXX-<slug>" in c or "in the worktree" in c


# ── Task 7: deliver-ticket.md — push transitions, document status-merge ──────
def test_deliver_pushes_terminal_status() -> None:
    c = read("context/flows/deliver-ticket.md")
    seg = c[c.index('XXXX → done'):]
    assert "git push" in seg[:400]


def test_deliver_documents_status_merge() -> None:
    c = read("context/flows/deliver-ticket.md").lower()
    assert "status merge" in c
    assert "no content conflict" in c or "no conflict" in c or "cleanly" in c


# ── Task 8: /abandon command + /cancel --abandon alias ──────────────────────
def test_abandon_command_exists() -> None:
    assert (ROOT / "commands/abandon.md").exists()


def test_abandon_sets_abandoned_status() -> None:
    c = read("commands/abandon.md")
    assert "status: abandoned" in c or "→ abandoned" in c


def test_abandon_distinct_from_cancelled() -> None:
    c = read("commands/abandon.md")
    assert "started but dropped" in c or "dropped" in c


def test_cancel_supports_abandon_alias() -> None:
    c = read("commands/cancel.md")
    assert "--abandon" in c
    assert "abandoned" in c
