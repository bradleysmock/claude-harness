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
