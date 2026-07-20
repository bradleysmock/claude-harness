# harness-combined/tests/test_ticket_module.py
import subprocess
from pathlib import Path

import pytest

import ticket


def _mk(root: Path, name: str) -> None:
    (root / name).mkdir(parents=True)
    (root / name / "status.md").write_text("status: solution\n", encoding="utf-8")


def _seed_claims(repo: Path, numbers: list[int]) -> None:
    """Append `claim` events for the given numbers directly to the ledger."""
    for n in numbers:
        ticket.ledger_append(
            repo,
            lambda recs, n=n: (
                [{
                    "event": "claim", "number": n, "slug": f"t{n}",
                    "title": f"T{n}", "owner": "a@x.c",
                    "branch": f"ticket/{n:04d}-t{n}", "ts": "t",
                }],
                None,
            ),
            push=False,
        )


def test_next_number_empty(tmp_path: Path) -> None:
    # NEW CONTRACT: next_number reads the .harness-tickets ledger, not .tickets/*.
    # A repo with no ledger (no claim ever made) starts at 1.
    repo = _init_repo(tmp_path)
    assert ticket.next_number(repo) == 1


def test_next_number_derives_from_ledger(tmp_path: Path) -> None:
    # NEW CONTRACT: was "scans .tickets/* + completed/*"; number allocation now
    # derives from the ledger's claim events (max(claim.number)+1). The old
    # filesystem scan survives only for one-time migration (see test file
    # test_harness_tickets_branch.py::test_migrate_seeds_from_filesystem).
    repo = _init_repo(tmp_path)
    _seed_claims(repo, [1, 3, 7])
    assert ticket.next_number(repo) == 8  # max(1,3,7)+1 from the ledger


def test_format_number_zero_pads() -> None:
    assert ticket.format_number(8) == "0008"


def test_parse_status_reads_fields(tmp_path: Path) -> None:
    f = tmp_path / "status.md"
    f.write_text("status: implementing\nticket: 0008\nowner: a@b.c\n", encoding="utf-8")
    parsed = ticket.parse_status(f)
    assert parsed["status"] == "implementing"
    assert parsed["owner"] == "a@b.c"


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    tdir = repo / ".tickets" / "0008-thing"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: solution\nticket: 0008\ntitle: Thing\n"
        "branch: ticket/0008-thing\nowner: dev@example.com\n"
        "source: local\nexternal_id:\nupdated: 2026-06-23\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


def test_owner_reads_git_email(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert ticket.owner(repo) == "dev@example.com"


def test_set_status_edits_and_commits(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ticket.set_status(repo, "0008", "implementing")
    parsed = ticket.parse_status(repo / ".tickets" / "0008-thing" / "status.md")
    assert parsed["status"] == "implementing"
    # working tree is clean — nothing orphaned
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert porcelain.strip() == ""
    subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert subject == "chore(ticket): 0008 → implementing"


def test_set_status_scopes_add(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "unrelated.txt").write_text("dirty", encoding="utf-8")  # untracked, must stay untracked
    ticket.set_status(repo, "0008", "review-ready")
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "unrelated.txt" in porcelain  # NOT swept into the commit


def _init_remote_clone(tmp_path: Path, name: str) -> tuple[Path, Path]:
    bare = tmp_path / "origin.git"
    if not bare.exists():
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    clone = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    subprocess.run(["git", "config", "user.email", f"{name}@x.c"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.name", name], cwd=clone, check=True)
    (clone / ".tickets").mkdir()
    (clone / ".tickets" / ".keep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=clone, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=clone, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD"], cwd=clone, check=True)
    return bare, clone


def _main_commit_count(repo: Path) -> int:
    return int(subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip())


def test_claim_writes_stub_on_branch_no_main_commit(tmp_path: Path) -> None:
    # NEW CONTRACT: claim no longer commits a stub to `main`. The number-allocation
    # arbiter is the `claim` line on the .harness-tickets ledger; the `claimed`
    # stub is written on the feature branch (its worktree), and `main` is untouched.
    _, clone = _init_remote_clone(tmp_path, "alice")
    main_before = _main_commit_count(clone)
    slug = ticket.claim(clone, "add-widget", "Add widget")
    # stub lives on the branch's worktree — NOT in main's working tree
    status_md = clone / ".worktrees" / slug / ".tickets" / slug / "status.md"
    parsed = ticket.parse_status(status_md)
    assert slug == "0001-add-widget"
    assert parsed["status"] == "claimed"
    assert parsed["owner"] == "alice@x.c"
    assert parsed["source"] == "local"
    # main got no new commit, and no active ticket dir landed on main
    assert _main_commit_count(clone) == main_before
    assert not (clone / ".tickets" / slug).exists()
    # the ledger records the claim (the arbiter)
    assert any(r["event"] == "claim" and r["number"] == 1 for r in ticket.ledger_read(clone))


def test_cli_claim_dispatches(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "cli"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "c@x.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "c"], cwd=repo, check=True)
    (repo / ".tickets").mkdir()
    (repo / ".tickets" / ".keep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    monkeypatch.chdir(repo)
    rc = ticket._main(["claim", "widget", "Widget"])
    assert rc == 0
    # NEW CONTRACT: the claimed stub is written on the branch's worktree, not main.
    assert (repo / ".worktrees" / "0001-widget" / ".tickets" / "0001-widget" / "status.md").exists()
    assert not (repo / ".tickets" / "0001-widget").exists()


def test_claim_renumbers_when_number_taken_on_push(tmp_path: Path) -> None:
    bare, alice = _init_remote_clone(tmp_path, "alice")
    bob = tmp_path / "bob"
    subprocess.run(["git", "clone", "-q", str(bare), str(bob)], check=True)
    subprocess.run(["git", "config", "user.email", "bob@x.c"], cwd=bob, check=True)
    subprocess.run(["git", "config", "user.name", "bob"], cwd=bob, check=True)

    alice_slug = ticket.claim(alice, "alpha", "Alpha", push=True)   # wins 0001, pushed
    bob_slug = ticket.claim(bob, "beta", "Beta", push=True)         # must renumber to 0002
    assert alice_slug == "0001-alpha"
    assert bob_slug == "0002-beta"
    # NEW CONTRACT: the winning stub lives on bob's feature branch worktree, not main
    stub = bob / ".worktrees" / bob_slug / ".tickets" / bob_slug / "status.md"
    assert stub.exists()
    assert ticket.parse_status(stub)["status"] == "claimed"


def _branch_exists(repo: Path, branch: str) -> bool:
    return bool(
        subprocess.run(
            ["git", "-C", str(repo), "branch", "--list", branch],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )


def test_claim_creates_branch_and_worktree_after_push(tmp_path: Path) -> None:
    _, alice = _init_remote_clone(tmp_path, "alice")
    slug = ticket.claim(alice, "widget", "Widget", push=True)
    assert slug == "0001-widget"
    # create-after-push: the winning claim has a branch and a worktree
    assert _branch_exists(alice, "ticket/0001-widget")
    assert (alice / ".worktrees" / "0001-widget").is_dir()


def test_claim_renumber_leaves_no_orphan_branch_or_worktree(tmp_path: Path) -> None:
    bare, alice = _init_remote_clone(tmp_path, "alice")
    bob = tmp_path / "bob"
    subprocess.run(["git", "clone", "-q", str(bare), str(bob)], check=True)
    subprocess.run(["git", "config", "user.email", "bob@x.c"], cwd=bob, check=True)
    subprocess.run(["git", "config", "user.name", "bob"], cwd=bob, check=True)

    ticket.claim(alice, "alpha", "Alpha", push=True)               # wins 0001
    bob_slug = ticket.claim(bob, "beta", "Beta", push=True)        # renumbers to 0002
    assert bob_slug == "0002-beta"
    # the dropped number 0001 must not have left a branch or worktree in bob's repo
    assert not _branch_exists(bob, "ticket/0001-beta")
    assert not (bob / ".worktrees" / "0001-beta").exists()
    # the winning number did get its branch + worktree
    assert _branch_exists(bob, "ticket/0002-beta")
    assert (bob / ".worktrees" / "0002-beta").is_dir()


def test_set_status_push_publishes_branch(tmp_path: Path) -> None:
    bare, dev = _init_remote_clone(tmp_path, "dev")
    # a branch-only ticket lives on its feature branch
    subprocess.run(["git", "-C", str(dev), "checkout", "-qb", "ticket/0005-x"], check=True)
    tdir = dev / ".tickets" / "0005-x"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: solution\nticket: 0005\ntitle: X\nbranch: ticket/0005-x\nowner: dev@x.c\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(dev), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(dev), "commit", "-qm", "seed branch"], check=True)

    ticket.set_status(dev, "0005", "implementing", push=True)  # branch-only, no upstream yet
    # origin now has the feature branch (upstream was set on first push)
    refs = subprocess.run(
        ["git", "-C", str(bare), "for-each-ref", "--format=%(refname)"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "refs/heads/ticket/0005-x" in refs


def test_deliver_squash_single_commit_with_done_archive(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    run("config", "user.email", "d@x.c")
    run("config", "user.name", "d")
    tdir = repo / ".tickets" / "0001-thing"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: claimed\nticket: 0001\ntitle: Thing\n"
        "branch: ticket/0001-thing\nowner: d@x.c\nupdated: 2026-06-23\n",
        encoding="utf-8",
    )
    run("add", "-A")
    run("commit", "-qm", "chore(ticket): 0001 claim")
    main_branch = run("rev-parse", "--abbrev-ref", "HEAD")
    claim_rev = run("rev-parse", "HEAD")

    # Feature branch: code change + branch-only review-ready transition.
    run("checkout", "-qb", "ticket/0001-thing")
    (repo / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tdir / "status.md").write_text(
        "status: review-ready\nticket: 0001\ntitle: Thing\n"
        "branch: ticket/0001-thing\nowner: d@x.c\nupdated: 2026-06-24\n",
        encoding="utf-8",
    )
    run("add", "-A")
    run("commit", "-qm", "feat: thing")
    run("checkout", "-q", main_branch)

    subject = ticket.deliver_squash(repo, "ticket/0001-thing", "0001-thing", "Thing")
    assert "(squash)" in subject

    # FR-1: exactly one commit on main since claim, and it is not a merge commit.
    assert run("rev-list", "--count", f"{claim_rev}..HEAD") == "1"
    assert run("rev-list", "--merges", "--count", f"{claim_rev}..HEAD") == "0"

    # FR-2: HEAD tree has the code diff + completed/<slug>/status.md (done), no <slug>/.
    tree = run("ls-tree", "-r", "--name-only", "HEAD")
    assert "feature.py" in tree
    assert ".tickets/completed/0001-thing/status.md" in tree
    assert ".tickets/0001-thing/status.md" not in tree
    done = run("show", "HEAD:.tickets/completed/0001-thing/status.md")
    assert "status: done" in done

    # the merged branch was deleted as part of delivery
    assert not _branch_exists(repo, "ticket/0001-thing")


def test_reopen_then_redeliver_adds_one_further_squash_commit(tmp_path: Path) -> None:
    """FR-6 git-sim: a delivered (archived) ticket is reopened onto a fresh branch
    forked from main HEAD, and a second deliver_squash adds exactly one more
    squashed commit on main (completed/<slug>/status.md back at done)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    run("config", "user.email", "d@x.c")
    run("config", "user.name", "d")

    # Prior delivery already happened: main has completed/<slug>/ (done) + code.
    completed = repo / ".tickets" / "completed" / "0001-thing"
    completed.mkdir(parents=True)
    (completed / "status.md").write_text(
        "status: done\nticket: 0001\ntitle: Thing\nbranch: ticket/0001-thing\nowner: d@x.c\n",
        encoding="utf-8",
    )
    (repo / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "feat: 0001-thing Thing (squash)")
    main_branch = run("rev-parse", "--abbrev-ref", "HEAD")
    delivered_rev = run("rev-parse", "HEAD")

    # /reopen: fresh branch from main HEAD; restore the dir onto the branch.
    run("checkout", "-qb", "ticket/0001-thing", main_branch)
    (repo / ".tickets" / "completed" / "0001-thing").rename(repo / ".tickets" / "0001-thing")
    tdir = repo / ".tickets" / "0001-thing"
    (tdir / "status.md").write_text(
        "status: solution\nticket: 0001\ntitle: Thing\nbranch: ticket/0001-thing\nowner: d@x.c\n",
        encoding="utf-8",
    )
    run("rm", "-r", "--cached", "--", ".tickets/completed/0001-thing/")
    run("add", "--", ".tickets/0001-thing/")
    run("commit", "-qm", "chore(ticket): 0001 → solution (reopened)")
    # further work on the reopened branch
    (repo / "feature.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tdir / "status.md").write_text(
        "status: review-ready\nticket: 0001\ntitle: Thing\nbranch: ticket/0001-thing\nowner: d@x.c\n",
        encoding="utf-8",
    )
    run("add", "-A")
    run("commit", "-qm", "feat: more work")
    run("checkout", "-q", main_branch)

    ticket.deliver_squash(repo, "ticket/0001-thing", "0001-thing", "Thing")

    # one further squash commit on main since the prior delivery, not a merge commit
    assert run("rev-list", "--count", f"{delivered_rev}..HEAD") == "1"
    assert run("rev-list", "--merges", "--count", f"{delivered_rev}..HEAD") == "0"
    tree = run("ls-tree", "-r", "--name-only", "HEAD")
    assert ".tickets/completed/0001-thing/status.md" in tree
    assert ".tickets/0001-thing/status.md" not in tree
    assert "status: done" in run("show", "HEAD:.tickets/completed/0001-thing/status.md")
    assert "VALUE = 2" in run("show", "HEAD:feature.py")  # the reopened work landed


def test_deliver_squash_preserves_branch_and_worktree_on_rejected_push(tmp_path: Path) -> None:
    """B-01 regression guard: when the publish is rejected (another developer
    advanced origin/main between the squash and the push), deliver_squash must
    raise and leave the branch + worktree intact — never destroy the only copy
    of the squashed commit's source history."""
    bare, dev = _init_remote_clone(tmp_path, "dev")

    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(dev), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    # Claim stub on dev's main, pushed so origin and dev agree.
    tdir = dev / ".tickets" / "0001-x"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: claimed\nticket: 0001\ntitle: X\nbranch: ticket/0001-x\nowner: dev@x.c\n",
        encoding="utf-8",
    )
    run("add", "-A")
    run("commit", "-qm", "chore(ticket): 0001 claim")
    run("push", "-q", "origin", "HEAD")
    main_branch = run("rev-parse", "--abbrev-ref", "HEAD")

    # Feature branch + worktree with code + branch-only review-ready.
    worktree = dev / ".worktrees" / "0001-x"
    run("worktree", "add", "-q", str(worktree), "-b", "ticket/0001-x")
    (worktree / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(worktree), "add", "-A"], check=True
    )
    subprocess.run(
        ["git", "-C", str(worktree), "commit", "-qm", "feat: x"], check=True
    )

    # Another developer advances origin/main, so dev's delivery push is non-fast-forward.
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True)
    subprocess.run(["git", "config", "user.email", "o@x.c"], cwd=other, check=True)
    subprocess.run(["git", "config", "user.name", "o"], cwd=other, check=True)
    (other / "unrelated.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(other), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(other), "commit", "-qm", "other work"], check=True)
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "HEAD"], check=True)

    head_before = run("rev-parse", "HEAD")
    with pytest.raises(RuntimeError):
        ticket.deliver_squash(dev, "ticket/0001-x", "0001-x", "X")

    # fail-closed: branch and worktree survive; the squash commit is preserved locally
    assert _branch_exists(dev, "ticket/0001-x")
    assert worktree.is_dir()
    assert run("rev-parse", "HEAD") != head_before  # the local squash commit was made
    assert main_branch  # sanity: we resolved the main branch name


def test_deliver_commit_alone_leaves_worktree_and_branch_unpushed(tmp_path: Path) -> None:
    """FR-1/2 gate invariant: `deliver_commit()` alone (no `deliver_publish()`)
    must leave the worktree and branch present and nothing pushed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    run("config", "user.email", "d@x.c")
    run("config", "user.name", "d")
    tdir = repo / ".tickets" / "0001-thing"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: claimed\nticket: 0001\ntitle: Thing\n"
        "branch: ticket/0001-thing\nowner: d@x.c\nupdated: 2026-06-23\n",
        encoding="utf-8",
    )
    run("add", "-A")
    run("commit", "-qm", "chore(ticket): 0001 claim")
    main_branch = run("rev-parse", "--abbrev-ref", "HEAD")

    worktree = repo / ".worktrees" / "0001-thing"
    run("worktree", "add", "-q", str(worktree), "-b", "ticket/0001-thing")
    (worktree / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (worktree / ".tickets" / "0001-thing" / "status.md").write_text(
        "status: review-ready\nticket: 0001\ntitle: Thing\n"
        "branch: ticket/0001-thing\nowner: d@x.c\nupdated: 2026-06-24\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(worktree), "commit", "-qm", "feat: thing"], check=True)
    run("checkout", "-q", main_branch)

    result = ticket.deliver_commit(repo, "ticket/0001-thing", "0001-thing", "Thing")
    assert "pre_merge_sha" in result and "merge_commit_sha" in result and "(squash)" in result["subject"]

    # gate invariant: worktree and branch both still present, HEAD unpushed
    assert _branch_exists(repo, "ticket/0001-thing")
    assert worktree.is_dir()
    tree = run("ls-tree", "-r", "--name-only", "HEAD")
    assert "feature.py" in tree
    assert ".tickets/completed/0001-thing/status.md" in tree


def test_deliver_publish_raises_and_preserves_on_rejected_push(tmp_path: Path) -> None:
    """`deliver_publish()` alone must raise and leave the worktree+branch intact
    on a rejected push — the other half of the FR-2 gate invariant."""
    bare, dev = _init_remote_clone(tmp_path, "dev")

    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(dev), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    tdir = dev / ".tickets" / "0001-x"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: claimed\nticket: 0001\ntitle: X\nbranch: ticket/0001-x\nowner: dev@x.c\n",
        encoding="utf-8",
    )
    run("add", "-A")
    run("commit", "-qm", "chore(ticket): 0001 claim")
    run("push", "-q", "origin", "HEAD")

    worktree = dev / ".worktrees" / "0001-x"
    run("worktree", "add", "-q", str(worktree), "-b", "ticket/0001-x")
    (worktree / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(worktree), "commit", "-qm", "feat: x"], check=True)

    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True)
    subprocess.run(["git", "config", "user.email", "o@x.c"], cwd=other, check=True)
    subprocess.run(["git", "config", "user.name", "o"], cwd=other, check=True)
    (other / "unrelated.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(other), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(other), "commit", "-qm", "other work"], check=True)
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "HEAD"], check=True)

    ticket.deliver_commit(dev, "ticket/0001-x", "0001-x", "X")
    head_before = run("rev-parse", "HEAD")
    with pytest.raises(RuntimeError):
        ticket.deliver_publish(dev, "0001-x", "ticket/0001-x")

    assert _branch_exists(dev, "ticket/0001-x")
    assert worktree.is_dir()
    assert run("rev-parse", "HEAD") == head_before


def test_cli_deliver_commit_and_publish_dispatch(tmp_path: Path, monkeypatch) -> None:
    """CLI subcommands `deliver-commit`/`deliver-publish` compose to the same
    end state as `deliver_squash()`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    run("config", "user.email", "d@x.c")
    run("config", "user.name", "d")
    tdir = repo / ".tickets" / "0001-thing"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: claimed\nticket: 0001\ntitle: Thing\n"
        "branch: ticket/0001-thing\nowner: d@x.c\nupdated: 2026-06-23\n",
        encoding="utf-8",
    )
    run("add", "-A")
    run("commit", "-qm", "chore(ticket): 0001 claim")
    main_branch = run("rev-parse", "--abbrev-ref", "HEAD")

    worktree = repo / ".worktrees" / "0001-thing"
    run("worktree", "add", "-q", str(worktree), "-b", "ticket/0001-thing")
    (worktree / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (worktree / ".tickets" / "0001-thing" / "status.md").write_text(
        "status: review-ready\nticket: 0001\ntitle: Thing\n"
        "branch: ticket/0001-thing\nowner: d@x.c\nupdated: 2026-06-24\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(worktree), "commit", "-qm", "feat: thing"], check=True)
    run("checkout", "-q", main_branch)

    monkeypatch.chdir(repo)
    rc = ticket._main(["deliver-commit", "ticket/0001-thing", "0001-thing", "Thing"])
    assert rc == 0
    # deliver-commit alone: branch/worktree still present (no remote, so publish is a no-op push)
    assert _branch_exists(repo, "ticket/0001-thing")

    rc = ticket._main(["deliver-publish", "0001-thing", "ticket/0001-thing"])
    assert rc == 0
    assert not _branch_exists(repo, "ticket/0001-thing")


# ── ticket 0070: nesting-aware worktree ticket-dir join point ─────────────

def _init_nested_repo(tmp_path: Path, subdir: str = "proj") -> Path:
    """A git repo whose `.tickets/` lives one level below the git top-level —
    mirrors this monorepo's `harness-combined/` subdirectory layout."""
    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=outer, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=outer, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=outer, check=True)
    repo = outer / subdir
    (repo / ".tickets").mkdir(parents=True)
    (repo / ".tickets" / ".keep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=outer, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=outer, check=True)
    return repo


def test_project_offset_flat_repo(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert ticket._project_offset(repo) == Path(".")


def test_project_offset_nested_repo(tmp_path: Path) -> None:
    repo = _init_nested_repo(tmp_path)
    assert ticket._project_offset(repo) == Path("proj")


def test_project_offset_outside_toplevel_raises_runtime_error(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    unrelated = tmp_path / "unrelated-toplevel"
    unrelated.mkdir()
    real_git = ticket.git

    def fake_git(r, *args, **kwargs):
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(args, 0, str(unrelated), "")
        return real_git(r, *args, **kwargs)

    monkeypatch.setattr(ticket, "git", fake_git)
    with pytest.raises(RuntimeError):
        ticket._project_offset(repo)


def test_worktree_ticket_dir_nested(tmp_path: Path) -> None:
    repo = _init_nested_repo(tmp_path)
    worktree = tmp_path / "wt"
    result = ticket._worktree_ticket_dir(repo, worktree, "0009-thing")
    assert result == worktree / "proj" / ".tickets" / "0009-thing"


def test_worktree_ticket_dir_flat(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    worktree = tmp_path / "wt"
    result = ticket._worktree_ticket_dir(repo, worktree, "0009-thing")
    assert result == worktree / ".tickets" / "0009-thing"


def test_create_branch_and_worktree_nested_writes_corrected_path(tmp_path: Path) -> None:
    repo = _init_nested_repo(tmp_path)
    ticket._create_branch_and_worktree(
        repo, "0001-widget", "widget", "Widget", "dev@example.com", push=False
    )
    worktree = repo / ".worktrees" / "0001-widget"
    status_md = worktree / "proj" / ".tickets" / "0001-widget" / "status.md"
    assert status_md.exists()
    assert "status: claimed" in status_md.read_text(encoding="utf-8")
    # never a stray root-level (un-offset) dir
    assert not (worktree / ".tickets").exists()
    # committed with a pathspec matching the corrected nested path
    log = subprocess.run(
        ["git", "-C", str(worktree), "show", "--stat", "--pretty=format:", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "proj/.tickets/0001-widget/status.md" in log


def test_create_branch_and_worktree_nested_resume_is_noop(tmp_path: Path) -> None:
    repo = _init_nested_repo(tmp_path)
    ticket._create_branch_and_worktree(
        repo, "0001-widget", "widget", "Widget", "dev@example.com", push=False
    )
    worktree = repo / ".worktrees" / "0001-widget"
    status_md = worktree / "proj" / ".tickets" / "0001-widget" / "status.md"
    before = status_md.read_text(encoding="utf-8")
    # resuming an already-claimed nested ticket must not duplicate or rewrite the stub
    ticket._create_branch_and_worktree(
        repo, "0001-widget", "widget", "Widget", "dev@example.com", push=False
    )
    assert status_md.read_text(encoding="utf-8") == before
    assert not (worktree / ".tickets").exists()


def test_read_ticket_docs_nested_reads_corrected_path(tmp_path: Path) -> None:
    repo = _init_nested_repo(tmp_path)
    # Build the corrected nested layout directly (not via _create_branch_and_worktree,
    # which — pre-fix — would write the same un-offset path _read_ticket_docs reads,
    # making this test pass vacuously either way).
    ticket_dir = repo / ".worktrees" / "0001-widget" / "proj" / ".tickets" / "0001-widget"
    ticket_dir.mkdir(parents=True)
    (ticket_dir / "status.md").write_text("status: claimed\n", encoding="utf-8")
    docs = ticket._read_ticket_docs(repo, "0001-widget", "ticket/0001-widget")
    assert "status.md" in docs
    assert "status: claimed" in docs["status.md"]


def test_reopen_nested_restores_at_corrected_path(tmp_path: Path) -> None:
    repo = _init_nested_repo(tmp_path)
    _seed_claims(repo, [9])
    completed = repo / ".tickets" / "completed" / "0009-t9"
    completed.mkdir(parents=True)
    (completed / "status.md").write_text(
        "status: done\nticket: 0009\ntitle: T9\nbranch: ticket/0009-t9\n"
        "owner: a@x.c\nupdated: 2026-07-01\n",
        encoding="utf-8",
    )
    full = ticket.reopen(repo, "0009", push=False)
    assert full == "0009-t9"
    status_md = repo / ".worktrees" / "0009-t9" / "proj" / ".tickets" / "0009-t9" / "status.md"
    assert status_md.exists()
    assert "status: solution" in status_md.read_text(encoding="utf-8")


def test_list_tickets_nested_reads_corrected_worktree_status(tmp_path: Path) -> None:
    repo = _init_nested_repo(tmp_path)
    _seed_claims(repo, [11])
    ticket._create_branch_and_worktree(
        repo, "0011-t11", "t11", "T11", "dev@example.com", push=False
    )
    rows = ticket.list_tickets(repo)
    row = next(r for r in rows if r["number"] == "0011")
    assert row["status"] == "claimed"
    assert row["updated"]


def test_list_tickets_nested_falls_back_to_legacy_path(tmp_path: Path) -> None:
    repo = _init_nested_repo(tmp_path)
    _seed_claims(repo, [12])
    legacy = repo / ".worktrees" / "0012-t12" / ".tickets" / "0012-t12"
    legacy.mkdir(parents=True)
    (legacy / "status.md").write_text(
        "status: implementing\nticket: 0012\ntitle: T12\nupdated: 2026-07-02\n",
        encoding="utf-8",
    )
    rows = ticket.list_tickets(repo)
    row = next(r for r in rows if r["number"] == "0012")
    assert row["status"] == "implementing"
    assert row["updated"] == "2026-07-02"


def test_list_tickets_routes_through_join_ticket_dir(tmp_path: Path, monkeypatch) -> None:
    repo = _init_nested_repo(tmp_path)
    _seed_claims(repo, [13])
    ticket._create_branch_and_worktree(
        repo, "0013-t13", "t13", "T13", "dev@example.com", push=False
    )
    calls: list[tuple] = []
    real_join = ticket._join_ticket_dir

    def counting_join(worktree, offset, slug):
        calls.append((worktree, offset, slug))
        return real_join(worktree, offset, slug)

    monkeypatch.setattr(ticket, "_join_ticket_dir", counting_join)
    ticket.list_tickets(repo)
    assert any(slug == "0013-t13" for (_w, _o, slug) in calls)


def test_list_tickets_calls_project_offset_once(tmp_path: Path, monkeypatch) -> None:
    repo = _init_nested_repo(tmp_path)
    _seed_claims(repo, [1, 2, 3])
    calls: list[Path] = []
    real_offset = ticket._project_offset

    def counting_offset(r):
        calls.append(r)
        return real_offset(r)

    monkeypatch.setattr(ticket, "_project_offset", counting_offset)
    ticket.list_tickets(repo)
    assert len(calls) == 1


def test_list_tickets_completed_includes_updated(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    completed = repo / ".tickets" / "completed" / "0020-done-thing"
    completed.mkdir(parents=True)
    (completed / "status.md").write_text(
        "status: done\nticket: 0020\ntitle: Done Thing\nupdated: 2026-05-05\n",
        encoding="utf-8",
    )
    rows = ticket.list_tickets(repo)
    row = next(r for r in rows if r["number"] == "0020")
    assert row["updated"] == "2026-05-05"
