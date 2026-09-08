# harness-combined/tests/test_ticket_commit_guard.py
import importlib.util
import subprocess
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "ticket_commit_guard", Path(__file__).parent.parent / "hooks" / "ticket_commit_guard.py"
)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "d@x.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "d"], cwd=repo, check=True)
    (repo / ".tickets" / "0001-x").mkdir(parents=True)
    (repo / ".tickets" / "0001-x" / "status.md").write_text("status: solution\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


def test_clean_tree_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert guard.dirty_ticket_files(repo) == []


def test_uncommitted_status_edit_is_flagged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".tickets" / "0001-x" / "status.md").write_text("status: implementing\n", encoding="utf-8")
    assert any("0001-x/status.md" in f for f in guard.dirty_ticket_files(repo))


def test_lock_and_active_sentinels_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".tickets" / ".ticket.lock").write_text("123:1", encoding="utf-8")
    (repo / ".tickets" / ".active").write_text("0001-x", encoding="utf-8")
    assert guard.dirty_ticket_files(repo) == []


def test_no_tickets_dir_is_noop(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    assert guard.dirty_ticket_files(repo) == []


def test_untracked_new_ticket_dir_is_flagged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    new_dir = repo / ".tickets" / "0002-fresh"
    new_dir.mkdir()
    (new_dir / "status.md").write_text("status: claimed\n", encoding="utf-8")
    assert any("0002-fresh" in f for f in guard.dirty_ticket_files(repo))


def _add_worktree(repo: Path, tmp_path: Path, name: str, branch: str) -> Path:
    wt = tmp_path / name
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-q", str(wt), "-b", branch],
        check=True,
    )
    return wt


def test_worktree_uncommitted_metadata_is_flagged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    wt = _add_worktree(repo, tmp_path, "wt", "ticket/0002-y")
    # a branch-only ticket dir lives only in the worktree, uncommitted
    (wt / ".tickets" / "0002-y").mkdir(parents=True)
    (wt / ".tickets" / "0002-y" / "status.md").write_text("status: solution\n", encoding="utf-8")
    # scanning from the main root discovers the worktree and flags it
    flagged = guard.dirty_ticket_files(repo)
    assert any("0002-y" in f for f in flagged)
    # the finding is attributed to the worktree, not to main's bare .tickets/ path
    assert all(not f.startswith(".tickets/0002-y") for f in flagged)


def test_guard_correct_when_cwd_is_the_worktree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    wt = _add_worktree(repo, tmp_path, "wt", "ticket/0003-z")
    (wt / ".tickets" / "0003-z").mkdir(parents=True)
    (wt / ".tickets" / "0003-z" / "status.md").write_text("status: implementing\n", encoding="utf-8")
    # the turn's cwd IS the worktree (ticket dir absent on main); still flagged
    flagged = guard.dirty_ticket_files(wt)
    assert any("0003-z" in f for f in flagged)


def test_clean_main_and_worktree_pass(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add_worktree(repo, tmp_path, "wt", "ticket/0004-clean")
    assert guard.dirty_ticket_files(repo) == []
