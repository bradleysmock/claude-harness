# harness-combined/tests/test_0069_ticket_cli_deliver.py
import subprocess
from pathlib import Path

import pytest

import ticket


def _record(**overrides) -> dict:
    base = {
        "event": "claim",
        "number": 69,
        "slug": "thing",
        "title": "Thing",
        "owner": "d@x.c",
        "branch": "ticket/0069-thing",
        "ts": "t",
    }
    base.update(overrides)
    return base


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """A `tmp_path/repo` with an initialized `.tickets/` dir, chdir'd into — the
    shared precondition `ticket._main(["deliver", ...])` needs so `find_tickets_root`
    resolves without touching the real repo."""
    r = tmp_path / "repo"
    r.mkdir()
    (r / ".tickets").mkdir()
    monkeypatch.chdir(r)
    return r


def test_deliver_cli_missing_ticket_id_exits_2(repo, monkeypatch, capsys) -> None:
    called = []
    monkeypatch.setattr(ticket, "_resolve_claim", lambda *a, **k: called.append(1))
    rc = ticket._main(["deliver"])
    assert rc == 2
    assert "usage" in capsys.readouterr().err
    assert called == []  # never attempted resolution


def test_deliver_cli_happy_path_calls_deliver_squash(repo, monkeypatch, capsys) -> None:
    monkeypatch.setattr(ticket, "_resolve_claim", lambda r, ident: _record())
    monkeypatch.setattr(
        ticket, "_read_ticket_docs",
        lambda r, full_slug, branch: {"status.md": "status: review-ready\nticket: 0069\n"},
    )
    calls = []

    def fake_deliver_squash(r, branch, slug, title):
        calls.append((branch, slug, title))
        return "feat: 0069-thing Thing (squash)"

    monkeypatch.setattr(ticket, "deliver_squash", fake_deliver_squash)

    rc = ticket._main(["deliver", "0069-thing"])
    assert rc == 0
    assert calls == [("ticket/0069-thing", "0069-thing", "Thing")]
    assert "feat: 0069-thing Thing (squash)" in capsys.readouterr().out


def test_deliver_cli_missing_status_md_is_file_not_found(repo, monkeypatch, capsys) -> None:
    monkeypatch.setattr(ticket, "_resolve_claim", lambda r, ident: _record())
    monkeypatch.setattr(ticket, "_read_ticket_docs", lambda r, full_slug, branch: {})

    def unexpected(*a, **k):
        raise AssertionError("deliver_squash must not be called")

    monkeypatch.setattr(ticket, "deliver_squash", unexpected)

    rc = ticket._main(["deliver", "0069-thing"])
    assert rc == 1
    assert capsys.readouterr().err.strip() != ""


def test_deliver_cli_wrong_status_does_not_deliver(repo, monkeypatch, capsys) -> None:
    monkeypatch.setattr(ticket, "_resolve_claim", lambda r, ident: _record())
    monkeypatch.setattr(
        ticket, "_read_ticket_docs",
        lambda r, full_slug, branch: {"status.md": "status: implementing\nticket: 0069\n"},
    )

    def unexpected(*a, **k):
        raise AssertionError("deliver_squash must not be called")

    monkeypatch.setattr(ticket, "deliver_squash", unexpected)

    rc = ticket._main(["deliver", "0069-thing"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "implementing" in err


def test_deliver_cli_unresolvable_ident_is_caught(repo, monkeypatch, capsys) -> None:
    def raise_not_found(r, ident):
        raise FileNotFoundError(f"no claim in the ledger for {ident!r}")

    monkeypatch.setattr(ticket, "_resolve_claim", raise_not_found)

    rc = ticket._main(["deliver", "bogus-id"])
    assert rc == 1
    assert capsys.readouterr().err.strip() != ""


def test_deliver_cli_runtime_error_from_deliver_squash_is_caught(repo, monkeypatch, capsys) -> None:
    monkeypatch.setattr(ticket, "_resolve_claim", lambda r, ident: _record())
    monkeypatch.setattr(
        ticket, "_read_ticket_docs",
        lambda r, full_slug, branch: {"status.md": "status: review-ready\nticket: 0069\n"},
    )

    def raise_runtime(r, branch, slug, title):
        raise RuntimeError("deliver_squash: pushing the squashed commit to origin was rejected")

    monkeypatch.setattr(ticket, "deliver_squash", raise_runtime)

    rc = ticket._main(["deliver", "0069-thing"])
    assert rc == 1
    assert "rejected" in capsys.readouterr().err


def test_deliver_cli_integration_full_flow(tmp_path: Path, monkeypatch) -> None:
    """CLI-level equivalent of test_deliver_squash_single_commit_with_done_archive:
    claim → hand-set review-ready on the branch → `ticket deliver <id>` → one
    squash commit, completed/<slug>/status.md at done, delivered ledger event."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "config", "user.email", "d@x.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "d"], cwd=repo, check=True)
    (repo / ".tickets").mkdir()
    (repo / ".tickets" / ".keep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)

    full_slug = ticket.claim(repo, "thing", "Thing")
    number = int(full_slug[:4])
    branch = f"ticket/{full_slug}"
    worktree = repo / ".worktrees" / full_slug

    (worktree / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    status_md = worktree / ".tickets" / full_slug / "status.md"
    status_md.write_text(
        f"status: review-ready\nticket: {full_slug[:4]}\ntitle: Thing\n"
        f"branch: {branch}\nowner: d@x.c\nupdated: 2026-07-19\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: thing"], cwd=worktree, check=True)

    main_branch = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", main_branch], check=True)

    monkeypatch.chdir(repo)
    rc = ticket._main(["deliver", full_slug])
    assert rc == 0

    tree = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "feature.py" in tree
    assert f".tickets/completed/{full_slug}/status.md" in tree
    assert f".tickets/{full_slug}/status.md" not in tree

    done = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:.tickets/completed/{full_slug}/status.md"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "status: done" in done

    assert any(
        r.get("event") == "delivered" and r.get("number") == number
        for r in ticket.ledger_read(repo)
    )
