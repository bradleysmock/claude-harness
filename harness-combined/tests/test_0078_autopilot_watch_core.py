"""Unit tests for autopilot_watch.py's pure scan/gate/dispatch-log core (ticket 0078).

Discovery is ledger-driven (reuses `ticket.list_tickets`/`ticket._project_offset`
rather than walking `.worktrees/*` by directory name), so a malformed or
unclaimed directory can never surface as a candidate. The approval gate is a
content-diff check, not a raw commit-equality check, because the
`approved-commit` field is written by a commit that is necessarily a
descendant of the SHA it records (see solution.md's Approach).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import autopilot_watch as watch
import ticket


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


def _seed_claim(repo: Path, number: int, slug: str) -> None:
    ticket.ledger_append(
        repo,
        lambda recs, number=number, slug=slug: (
            [{
                "event": "claim", "number": number, "slug": slug,
                "title": slug, "owner": "dev@example.com",
                "branch": f"ticket/{number:04d}-{slug}", "ts": "t",
            }],
            None,
        ),
        push=False,
    )


def _seed_ticket_branch_and_worktree(
    repo: Path, number: int, slug: str, status_fields: dict[str, str]
) -> tuple[Path, Path]:
    full = f"{number:04d}-{slug}"
    branch = f"ticket/{full}"
    subprocess.run(["git", "branch", branch], cwd=repo, check=True)
    worktree = repo / ".worktrees" / full
    subprocess.run(["git", "worktree", "add", "-q", str(worktree), branch], cwd=repo, check=True)
    ticket_dir = worktree / ".tickets" / full
    ticket_dir.mkdir(parents=True)
    for name in ("problem.md", "requirements.md", "solution.md"):
        (ticket_dir / name).write_text(f"{name} v1\n", encoding="utf-8")
    lines = "\n".join(f"{key}: {value}" for key, value in status_fields.items())
    (ticket_dir / "status.md").write_text(lines + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-qm", "design"], cwd=worktree, check=True)
    return worktree, ticket_dir


def _head(worktree: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _approve(worktree: Path, ticket_dir: Path, approved_commit: str) -> None:
    text = (ticket_dir / "status.md").read_text(encoding="utf-8")
    text = text.rstrip("\n") + f"\napproved-at: 2026-09-10\napproved-commit: {approved_commit}\n"
    (ticket_dir / "status.md").write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(worktree), "commit", "-qm", "chore: approve"], check=True)


def _base_fields(number: int, slug: str) -> dict[str, str]:
    full = f"{number:04d}-{slug}"
    return {
        "status": "solution", "ticket": f"{number:04d}", "title": slug,
        "branch": f"ticket/{full}", "owner": "dev@example.com",
        "source": "local", "external_id": "", "updated": "2026-09-10",
        "approved-at": "", "approved-commit": "",
    }


# ---------------------------------------------------------------------------
# scan / discovery
# ---------------------------------------------------------------------------


def test_scan_ignores_unclaimed_directory(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / ".worktrees" / "not-a-ticket").mkdir(parents=True)
    assert watch.scan_worktree_tickets(repo) == []


def test_scan_finds_claimed_ticket(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    found = watch.scan_worktree_tickets(repo)
    assert [t.number for t in found] == ["0001"]
    assert found[0].status == "solution"


# ---------------------------------------------------------------------------
# approval gate (find_dispatchable)
# ---------------------------------------------------------------------------


def test_excludes_ticket_with_blank_approved_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    assert watch.find_dispatchable(repo) == []


def test_dispatches_ticket_approved_at_current_head_real_sequence(tmp_path: Path) -> None:
    """Replays the actual /problem Checkpoint 1 sequence: a design commit,
    then a separate commit that writes approved-at/approved-commit pointing
    at the *pre-approval* HEAD. Raw HEAD == approved-commit would never hold
    here (approval-write is a descendant of design); the content-diff gate
    must still pass because neither commit touched the three design files
    after the SHA being recorded."""
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    design_sha = _head(worktree)
    _approve(worktree, ticket_dir, design_sha)
    assert design_sha != _head(worktree)  # sanity: approval-write really is a new commit
    result = watch.find_dispatchable(repo)
    assert [t.number for t in result] == ["0001"]


def test_excludes_ticket_with_content_drift_after_approval(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    design_sha = _head(worktree)
    _approve(worktree, ticket_dir, design_sha)
    (ticket_dir / "solution.md").write_text("solution.md v2 — unapproved edit\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "commit", "-am", "edit after approval"], check=True)
    assert watch.find_dispatchable(repo) == []


def test_excludes_approved_commit_not_ancestor_of_head(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    fake_sha = "abc1234"
    _approve(worktree, ticket_dir, fake_sha)
    assert watch.find_dispatchable(repo) == []


def test_reopen_same_day_reapproval_dispatches_with_new_sha(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    first_sha = _head(worktree)
    _approve(worktree, ticket_dir, first_sha)

    dispatch_log = {("0001", first_sha)}  # already dispatched at the first approval

    (ticket_dir / "solution.md").write_text("solution.md v2 — reopened\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "commit", "-am", "reopen revision"], check=True)
    second_sha = _head(worktree)
    _approve(worktree, ticket_dir, second_sha)

    result = watch.find_dispatchable(repo, dispatch_log)
    assert [(t.number, t.approved_commit) for t in result] == [("0001", second_sha)]


def test_dispatch_log_excludes_already_dispatched_pair(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    sha = _head(worktree)
    _approve(worktree, ticket_dir, sha)
    assert watch.find_dispatchable(repo, {("0001", sha)}) == []


# ---------------------------------------------------------------------------
# dispatch log persistence
# ---------------------------------------------------------------------------


def test_dispatch_log_roundtrip(tmp_path: Path) -> None:
    log_path = tmp_path / "log.jsonl"
    assert watch.load_dispatch_log(log_path) == set()
    watch.record_dispatch(log_path, "0001", "abcdef1")
    watch.record_dispatch(log_path, "0002", "1234567")
    assert watch.load_dispatch_log(log_path) == {("0001", "abcdef1"), ("0002", "1234567")}


# ---------------------------------------------------------------------------
# run_tick
# ---------------------------------------------------------------------------


def test_run_tick_no_candidates_returns_none(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=lambda t: 0)
    assert result == {"dispatched": None, "error": None}


def test_run_tick_records_dispatch_before_invoking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    sha = _head(worktree)
    _approve(worktree, ticket_dir, sha)
    log_path = tmp_path / "log.jsonl"

    seen_log_state = {}

    def failing_dispatch(t: watch.TicketInfo) -> int:
        seen_log_state["logged_before_dispatch"] = watch.load_dispatch_log(log_path)
        raise FileNotFoundError("claude: command not found")

    result = watch.run_tick(repo, log_path, dispatch=failing_dispatch)
    assert result["dispatched"] == "0001"
    assert "claude" in result["error"]
    assert ("0001", sha) in seen_log_state["logged_before_dispatch"]
    assert ("0001", sha) in watch.load_dispatch_log(log_path)


def test_run_tick_propagates_non_os_error_from_dispatch(tmp_path: Path) -> None:
    """Only OSError (an expected subprocess-launch failure) is caught inside
    run_tick — a genuine bug in the dispatch callable still propagates, so
    it isn't silently absorbed. The dispatch log entry survives regardless
    (it was already written before dispatch ran)."""
    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    sha = _head(worktree)
    _approve(worktree, ticket_dir, sha)
    log_path = tmp_path / "log.jsonl"

    def buggy_dispatch(t: watch.TicketInfo) -> int:
        raise ValueError("not a subprocess-launch failure")

    with pytest.raises(ValueError):
        watch.run_tick(repo, log_path, dispatch=buggy_dispatch)
    assert ("0001", sha) in watch.load_dispatch_log(log_path)


def test_run_tick_picks_lowest_ticket_number(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    for number in (2, 1):
        _seed_claim(repo, number, f"t{number}")
        worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, number, f"t{number}", _base_fields(number, f"t{number}"))
        _approve(worktree, ticket_dir, _head(worktree))
    dispatched: list[str] = []
    result = watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=lambda t: dispatched.append(t.number))
    assert result["dispatched"] == "0001"
    assert dispatched == ["0001"]


# ---------------------------------------------------------------------------
# PID lifecycle + status snapshot
# ---------------------------------------------------------------------------


def test_pid_is_alive_true_for_current_process() -> None:
    assert watch.pid_is_alive(os.getpid()) is True


def test_pid_is_alive_false_for_exited_process() -> None:
    proc = subprocess.Popen(["true"])
    proc.wait()
    assert watch.pid_is_alive(proc.pid) is False


def test_pid_file_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "watch.pid"
    assert watch.read_pid_file(path) is None
    watch.write_pid_file(path, 4242)
    assert watch.read_pid_file(path) == 4242
    watch.remove_pid_file(path)
    assert watch.read_pid_file(path) is None


def test_pid_file_malformed_reads_as_none(tmp_path: Path) -> None:
    path = tmp_path / "watch.pid"
    path.write_text("not-a-pid", encoding="utf-8")
    assert watch.read_pid_file(path) is None


def test_status_snapshot_defaults_when_missing(tmp_path: Path) -> None:
    snapshot = watch.read_status_snapshot(tmp_path / "status.json")
    assert snapshot == {
        "running": False, "pid": None, "last_tick": None, "last_dispatch_outcome": None,
    }


def test_status_snapshot_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    watch.write_status_snapshot(path, running=True, pid=123, last_tick="2026-09-10T00:00:00", last_dispatch_outcome="0")
    snapshot = watch.read_status_snapshot(path)
    assert snapshot["running"] is True
    assert snapshot["pid"] == 123
    assert snapshot["last_dispatch_outcome"] == "0"
