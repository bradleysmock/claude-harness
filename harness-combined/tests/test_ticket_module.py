# harness-combined/tests/test_ticket_module.py
import subprocess
from pathlib import Path

import ticket


def _mk(root: Path, name: str) -> None:
    (root / name).mkdir(parents=True)
    (root / name / "status.md").write_text("status: solution\n", encoding="utf-8")


def test_next_number_empty(tmp_path: Path) -> None:
    (tmp_path / ".tickets").mkdir()
    assert ticket.next_number(tmp_path / ".tickets") == 1


def test_next_number_scans_active_and_completed(tmp_path: Path) -> None:
    tickets = tmp_path / ".tickets"
    _mk(tickets, "0001-alpha")
    _mk(tickets, "completed/0007-archived")
    _mk(tickets, "0003-beta")
    assert ticket.next_number(tickets) == 8  # max(1,3,7)+1, completed counts


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


def test_claim_writes_stub_and_commits(tmp_path: Path) -> None:
    _, clone = _init_remote_clone(tmp_path, "alice")
    slug = ticket.claim(clone, "add-widget", "Add widget")
    status_md = clone / ".tickets" / slug / "status.md"
    parsed = ticket.parse_status(status_md)
    assert slug == "0001-add-widget"
    assert parsed["status"] == "claimed"
    assert parsed["owner"] == "alice@x.c"
    assert parsed["source"] == "local"


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
    assert (repo / ".tickets" / "0001-widget" / "status.md").exists()


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
    assert (bob / ".tickets" / bob_slug / "status.md").exists()
    assert ticket.parse_status(bob / ".tickets" / bob_slug / "status.md")["status"] == "claimed"


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
