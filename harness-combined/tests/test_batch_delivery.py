# harness-combined/tests/test_batch_delivery.py
"""Git-sim tests for batch delivery (`ticket.deliver_squash_batch`).

Autopilot batch mode builds several related tickets into one integration
worktree/branch, tests them together, then delivers them as one squashed commit
*per member* in a single atomic push. These tests pin that contract:

  - N members -> exactly N commits on main, none of them merge commits;
  - each member's commit carries only that member's code delta + its own
    `completed/<slug>/` archive at `done` (no sibling bleed);
  - integration repairs made after the last member's boundary fold into the
    last member's commit;
  - a clean delivery removes the batch branch and each member's vestigial
    per-ticket branch/worktree;
  - a rejected push leaves the whole batch intact (fail-closed).

Mirrors the git-sim style in tests/test_ticket_module.py.
"""
import json
import subprocess
from pathlib import Path

import pytest

import ticket


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _stub(text_status: str, number: str, title: str, slug: str) -> str:
    return (
        f"status: {text_status}\nticket: {number}\ntitle: {title}\n"
        f"branch: ticket/{number}-{slug}\nowner: d@x.c\n"
        f"source: local\nexternal_id:\nupdated: 2026-07-08\n"
    )


def _init_main_with_claims(repo: Path, members: list[tuple[str, str, str]]) -> str:
    """Init a repo whose `main` carries a `claimed` stub for each member.

    members: list of (number, slug, title). Returns the claim-base rev.
    """
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "d@x.c")
    _git(repo, "config", "user.name", "d")
    for number, slug, title in members:
        tdir = repo / ".tickets" / f"{number}-{slug}"
        tdir.mkdir(parents=True)
        (tdir / "status.md").write_text(_stub("claimed", number, title, slug), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "chore(ticket): claims")
    return _git(repo, "rev-parse", "HEAD")


def _build_member_range(repo: Path, number: str, slug: str, title: str) -> str:
    """Simulate one member's build on the current (batch) branch: import its
    design dir at review-ready + write its code file, as one commit. Returns the
    boundary rev (HEAD after the member's range)."""
    tdir = repo / ".tickets" / f"{number}-{slug}"
    (tdir / "status.md").write_text(_stub("review-ready", number, title, slug), encoding="utf-8")
    (tdir / "solution.md").write_text(f"# {title}\n", encoding="utf-8")
    (repo / f"{slug}.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"feat: {number} {slug}")
    return _git(repo, "rev-parse", "HEAD")


def _branch_exists(repo: Path, branch: str) -> bool:
    return bool(_git(repo, "branch", "--list", branch))


def test_batch_delivers_one_commit_per_member(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    claim_base = _init_main_with_claims(
        repo, [("0001", "alpha", "Alpha"), ("0002", "beta", "Beta")]
    )
    main = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    _git(repo, "checkout", "-qb", "batch/0001-alpha")
    b1 = _build_member_range(repo, "0001", "alpha", "Alpha")
    b2 = _build_member_range(repo, "0002", "beta", "Beta")
    _git(repo, "checkout", "-q", main)

    members = [
        {"slug": "0001-alpha", "title": "Alpha", "head": b1},
        {"slug": "0002-beta", "title": "Beta", "head": b2},
    ]
    subjects = ticket.deliver_squash_batch(repo, "batch/0001-alpha", members)
    assert subjects == ["feat: 0001-alpha Alpha (squash)", "feat: 0002-beta Beta (squash)"]

    # exactly two commits since the claim base, neither a merge commit
    assert _git(repo, "rev-list", "--count", f"{claim_base}..HEAD") == "2"
    assert _git(repo, "rev-list", "--merges", "--count", f"{claim_base}..HEAD") == "0"

    # first delivery commit (0001): alpha.py + completed/0001-alpha at done,
    # and NO beta bleed, NO active 0001 dir.
    first = _git(repo, "rev-parse", "HEAD~1")
    first_tree = _git(repo, "ls-tree", "-r", "--name-only", first)
    assert "alpha.py" in first_tree
    assert "beta.py" not in first_tree
    assert ".tickets/completed/0001-alpha/status.md" in first_tree
    assert ".tickets/0001-alpha/status.md" not in first_tree
    assert "status: done" in _git(repo, "show", f"{first}:.tickets/completed/0001-alpha/status.md")

    # second delivery commit (0002): beta.py + completed/0002-beta at done
    head_tree = _git(repo, "ls-tree", "-r", "--name-only", "HEAD")
    assert "beta.py" in head_tree
    assert "alpha.py" in head_tree  # cumulative
    assert ".tickets/completed/0002-beta/status.md" in head_tree
    assert ".tickets/0002-beta/status.md" not in head_tree
    assert "status: done" in _git(repo, "show", "HEAD:.tickets/completed/0002-beta/status.md")

    # both members archived; no active ticket dirs remain
    assert ".tickets/0001-alpha/status.md" not in head_tree
    assert ".tickets/completed/0001-alpha/status.md" in head_tree


def test_batch_cleans_up_batch_and_member_branches(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_main_with_claims(repo, [("0001", "alpha", "Alpha"), ("0002", "beta", "Beta")])
    main = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    # vestigial per-ticket branches (created at claim time in real life)
    _git(repo, "branch", "ticket/0001-alpha", main)
    _git(repo, "branch", "ticket/0002-beta", main)

    _git(repo, "checkout", "-qb", "batch/0001-alpha")
    b1 = _build_member_range(repo, "0001", "alpha", "Alpha")
    b2 = _build_member_range(repo, "0002", "beta", "Beta")
    _git(repo, "checkout", "-q", main)

    members = [
        {"slug": "0001-alpha", "title": "Alpha", "head": b1},
        {"slug": "0002-beta", "title": "Beta", "head": b2},
    ]
    ticket.deliver_squash_batch(repo, "batch/0001-alpha", members)

    assert not _branch_exists(repo, "batch/0001-alpha")
    assert not _branch_exists(repo, "ticket/0001-alpha")
    assert not _branch_exists(repo, "ticket/0002-beta")


def test_batch_integration_repairs_fold_into_last_member(tmp_path: Path) -> None:
    """A fix committed after the last member's build (combined-critic repair)
    folds into the last member's delivery commit — total commit count stays N."""
    repo = tmp_path / "repo"
    claim_base = _init_main_with_claims(
        repo, [("0001", "alpha", "Alpha"), ("0002", "beta", "Beta")]
    )
    main = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    _git(repo, "checkout", "-qb", "batch/0001-alpha")
    b1 = _build_member_range(repo, "0001", "alpha", "Alpha")
    _build_member_range(repo, "0002", "beta", "Beta")
    # combined-critic repair touching an earlier member's file, after member 2's boundary
    (repo / "alpha.py").write_text("VALUE = 99\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fix: integration repair")
    repaired_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", main)

    members = [
        {"slug": "0001-alpha", "title": "Alpha", "head": b1},
        {"slug": "0002-beta", "title": "Beta", "head": repaired_head},
    ]
    ticket.deliver_squash_batch(repo, "batch/0001-alpha", members)

    # still exactly two commits; the repair landed (folded into member 2's commit)
    assert _git(repo, "rev-list", "--count", f"{claim_base}..HEAD") == "2"
    assert "VALUE = 99" in _git(repo, "show", "HEAD:alpha.py")


def test_batch_rejected_push_leaves_everything_intact(tmp_path: Path) -> None:
    """When the atomic push is rejected, deliver_squash_batch raises and leaves
    the batch branch (and any staged/committed delivery) recoverable — it must
    not delete the only copy of the work. Fail-closed, mirroring deliver_squash."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)

    repo = tmp_path / "repo"
    _init_main_with_claims(repo, [("0001", "alpha", "Alpha")])
    main = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", main)

    # origin advances so our push is rejected (non-fast-forward)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "config", "user.email", "e@x.c")
    _git(other, "config", "user.name", "e")
    (other / "unrelated.txt").write_text("x\n", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-qm", "advance origin")
    _git(other, "push", "-q", "origin", main)

    _git(repo, "checkout", "-qb", "batch/0001-alpha")
    b1 = _build_member_range(repo, "0001", "alpha", "Alpha")
    _git(repo, "checkout", "-q", main)

    members = [{"slug": "0001-alpha", "title": "Alpha", "head": b1}]
    with pytest.raises(RuntimeError):
        ticket.deliver_squash_batch(repo, "batch/0001-alpha", members)

    # fail-closed: the batch branch survives so the lead can rebase and retry
    assert _branch_exists(repo, "batch/0001-alpha")


def test_deliver_batch_cli_reads_members_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `deliver-batch` CLI reads members from a JSON file and delivers."""
    repo = tmp_path / "repo"
    _init_main_with_claims(repo, [("0001", "alpha", "Alpha"), ("0002", "beta", "Beta")])
    main = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    _git(repo, "checkout", "-qb", "batch/0001-alpha")
    b1 = _build_member_range(repo, "0001", "alpha", "Alpha")
    b2 = _build_member_range(repo, "0002", "beta", "Beta")
    _git(repo, "checkout", "-q", main)

    members_file = repo / "members.json"
    members_file.write_text(
        json.dumps(
            [
                {"slug": "0001-alpha", "title": "Alpha", "head": b1},
                {"slug": "0002-beta", "title": "Beta", "head": b2},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)  # _main resolves the repo from cwd
    rc = ticket._main(["deliver-batch", "batch/0001-alpha", str(members_file)])
    assert rc == 0
    assert not _branch_exists(repo, "batch/0001-alpha")
