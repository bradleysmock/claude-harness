"""Unit tests for autopilot_watch.py's pure scan/gate/dispatch-log core (ticket 0078).

Discovery is ledger-driven (reuses `ticket.list_tickets`/`ticket._project_offset`
rather than walking `.worktrees/*` by directory name), so a malformed or
unclaimed directory can never surface as a candidate. The approval gate is a
content-diff check, not a raw commit-equality check, because the
`approved-commit` field is written by a commit that is necessarily a
descendant of the SHA it records (see solution.md's Approach).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from _watch_fixtures import (
    approve,
    base_fields,
    head,
    init_repo,
    seed_claim,
    seed_ticket_branch_and_worktree,
)

import autopilot_watch as watch

# ---------------------------------------------------------------------------
# scan / discovery
# ---------------------------------------------------------------------------


def test_scan_ignores_unclaimed_directory(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / ".worktrees" / "not-a-ticket").mkdir(parents=True)
    assert watch.scan_worktree_tickets(repo) == []


def test_scan_finds_claimed_ticket(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    found = watch.scan_worktree_tickets(repo)
    assert [t.number for t in found] == ["0001"]
    assert found[0].status == "solution"


# ---------------------------------------------------------------------------
# approval gate (find_dispatchable)
# ---------------------------------------------------------------------------


def test_excludes_ticket_with_blank_approved_commit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    assert watch.find_dispatchable(repo) == []


def test_dispatches_ticket_approved_at_current_head_real_sequence(tmp_path: Path) -> None:
    """Replays the actual /problem Checkpoint 1 sequence: a design commit,
    then a separate commit that writes approved-at/approved-commit pointing
    at the *pre-approval* HEAD. Raw HEAD == approved-commit would never hold
    here (approval-write is a descendant of design); the content-diff gate
    must still pass because neither commit touched the three design files
    after the SHA being recorded."""
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    design_sha = head(worktree)
    approve(worktree, ticket_dir, design_sha)
    assert design_sha != head(worktree)  # sanity: approval-write really is a new commit
    result = watch.find_dispatchable(repo)
    assert [t.number for t in result] == ["0001"]


def test_excludes_ticket_with_content_drift_after_approval(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    design_sha = head(worktree)
    approve(worktree, ticket_dir, design_sha)
    (ticket_dir / "solution.md").write_text("solution.md v2 — unapproved edit\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "commit", "-am", "edit after approval"], check=True)
    assert watch.find_dispatchable(repo) == []


def test_content_drift_after_approval_is_logged(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    design_sha = head(worktree)
    approve(worktree, ticket_dir, design_sha)
    (ticket_dir / "solution.md").write_text("solution.md v2 — unapproved edit\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "commit", "-am", "edit after approval"], check=True)
    watch.find_dispatchable(repo)
    rejections = (repo / ".harness" / "autopilot-watch" / "rejections.log").read_text(encoding="utf-8")
    record = json.loads(rejections.strip().splitlines()[-1])
    assert record["ticket"] == "0001"
    assert "drift" in record["reason"]


def test_excludes_approved_commit_not_ancestor_of_head(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    fake_sha = "abc1234"
    approve(worktree, ticket_dir, fake_sha)
    assert watch.find_dispatchable(repo) == []


def test_reopen_same_day_reapproval_dispatches_with_new_sha(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    first_sha = head(worktree)
    approve(worktree, ticket_dir, first_sha)

    dispatch_log = {("0001", first_sha)}  # already dispatched at the first approval

    (ticket_dir / "solution.md").write_text("solution.md v2 — reopened\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "commit", "-am", "reopen revision"], check=True)
    second_sha = head(worktree)
    approve(worktree, ticket_dir, second_sha)

    result = watch.find_dispatchable(repo, dispatch_log)
    assert [(t.number, t.approved_commit) for t in result] == [("0001", second_sha)]


def test_dispatch_log_excludes_already_dispatched_pair(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    sha = head(worktree)
    approve(worktree, ticket_dir, sha)
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


def test_default_dispatch_uses_fully_qualified_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a bare `/autopilot` command does not resolve in headless
    `claude -p` mode (verified live) — the dispatched command must be the
    fully-qualified `/harness-combined:autopilot <number>` form."""
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    ticket_info = watch.scan_worktree_tickets(repo)[0]

    captured: dict[str, list[str]] = {}

    class _FakeCompleted:
        returncode = 0

    def fake_run(args: list[str], **kwargs: object) -> _FakeCompleted:
        captured["args"] = args
        return _FakeCompleted()

    monkeypatch.setattr(watch.subprocess, "run", fake_run)
    watch.default_dispatch(ticket_info, repo)

    assert captured["args"][0] == "claude"
    assert captured["args"][1] == "-p"
    assert captured["args"][2] == "/harness-combined:autopilot 0001"


def test_run_tick_no_candidates_returns_none(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    result = watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=lambda t: 0)
    assert result == {"dispatched": None, "error": None, "exit_code": None}


def test_run_tick_surfaces_dispatch_exit_code(tmp_path: Path) -> None:
    """A dispatch that "succeeds" (no exception) but exits non-zero — e.g. the
    autopilot build itself failed — must not read the same as a clean run."""
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    sha = head(worktree)
    approve(worktree, ticket_dir, sha)
    result = watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=lambda t: 1)
    assert result == {"dispatched": "0001", "error": None, "exit_code": 1}


def test_run_tick_records_dispatch_before_invoking(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    sha = head(worktree)
    approve(worktree, ticket_dir, sha)
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
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    sha = head(worktree)
    approve(worktree, ticket_dir, sha)
    log_path = tmp_path / "log.jsonl"

    def buggy_dispatch(t: watch.TicketInfo) -> int:
        raise ValueError("not a subprocess-launch failure")

    with pytest.raises(ValueError):
        watch.run_tick(repo, log_path, dispatch=buggy_dispatch)
    assert ("0001", sha) in watch.load_dispatch_log(log_path)


def test_run_tick_picks_lowest_ticket_number(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    for number in (2, 1):
        seed_claim(repo, number, f"t{number}")
        worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, number, f"t{number}", base_fields(number, f"t{number}"))
        approve(worktree, ticket_dir, head(worktree))
    dispatched: list[str] = []

    def record_and_succeed(t: watch.TicketInfo) -> int:
        dispatched.append(t.number)
        return 0

    result = watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=record_and_succeed)
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
