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
