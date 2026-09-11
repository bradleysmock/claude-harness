"""Tests for wiring needs-attention detection into `run_tick` and `cli_status`
(ticket 0082).

`run_tick` already dispatched and blocked; what ticket 0078 left missing is any
signal about how the dispatch *ended*. These tests pin that signal to the
ticket's on-disk `status.md` — the dispatch callable is a stub that rewrites
`status.md` the way a real `/autopilot` run would, so the assertions exercise the
same structural path production takes rather than a mocked classifier.
"""

from __future__ import annotations

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
# helpers
# ---------------------------------------------------------------------------


def seed_dispatchable(tmp_path: Path) -> tuple[Path, Path]:
    """A repo with ticket 0001 claimed, approved, and ready to dispatch."""
    repo = init_repo(tmp_path)
    seed_claim(repo, 1, "foo")
    worktree, ticket_dir = seed_ticket_branch_and_worktree(repo, 1, "foo", base_fields(1, "foo"))
    approve(worktree, ticket_dir, head(worktree))
    return repo, ticket_dir


def set_status(ticket_dir: Path, status: str) -> None:
    """Rewrite `status.md`'s `status:` line the way a real dispatch would."""
    lines = (ticket_dir / "status.md").read_text(encoding="utf-8").splitlines()
    rewritten = [
        f"status: {status}" if line.startswith("status:") else line for line in lines
    ]
    (ticket_dir / "status.md").write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def leaving_status(ticket_dir: Path, status: str):
    """A dispatch stub that lands the ticket on `status` and exits cleanly."""

    def dispatch(ticket_info: watch.TicketInfo) -> int:
        set_status(ticket_dir, status)
        return 0

    return dispatch


def attention_entries(repo: Path) -> list[dict[str, object]]:
    return watch._load_needs_attention(watch._needs_attention_path(repo))


@pytest.fixture
def captured_notifications(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Intercept `_notify_desktop` so tests assert *that* it fired, not that a
    real notifier is installed on the machine running the suite."""
    fired: list[tuple[str, str]] = []
    monkeypatch.setattr(
        watch, "_notify_desktop", lambda number, reason: fired.append((number, reason))
    )
    return fired


# ---------------------------------------------------------------------------
# run_tick — return shape
# ---------------------------------------------------------------------------


def test_run_tick_no_candidates_carries_the_widened_shape(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    result = watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=lambda t: 0)
    assert result == {
        "dispatched": None,
        "error": None,
        "exit_code": None,
        "needs_attention": False,
        "reason": None,
    }


def test_run_tick_no_candidates_logs_nothing(tmp_path: Path) -> None:
    """A quiet tick is not an attention event — nothing to look at, nothing
    logged, nothing notified."""
    repo = init_repo(tmp_path)
    watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=lambda t: 0)
    assert attention_entries(repo) == []


# ---------------------------------------------------------------------------
# run_tick — success
# ---------------------------------------------------------------------------


def test_run_tick_done_is_success_and_silent(
    tmp_path: Path, captured_notifications: list[tuple[str, str]]
) -> None:
    repo, ticket_dir = seed_dispatchable(tmp_path)
    result = watch.run_tick(
        repo, tmp_path / "log.jsonl", dispatch=leaving_status(ticket_dir, "done")
    )
    assert result["dispatched"] == "0001"
    assert result["needs_attention"] is False
    assert result["reason"] is None
    assert attention_entries(repo) == []
    assert captured_notifications == []


# ---------------------------------------------------------------------------
# run_tick — needs attention
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", ["changes-requested", "solution", "implementing", "review-ready"]
)
def test_run_tick_non_done_status_logs_once_and_notifies(
    tmp_path: Path, captured_notifications: list[tuple[str, str]], status: str
) -> None:
    repo, ticket_dir = seed_dispatchable(tmp_path)
    result = watch.run_tick(
        repo, tmp_path / "log.jsonl", dispatch=leaving_status(ticket_dir, status)
    )

    assert result["needs_attention"] is True
    assert result["reason"]
    assert status in str(result["reason"])

    entries = attention_entries(repo)
    assert len(entries) == 1
    assert entries[0]["ticket"] == "0001"
    assert entries[0]["reason"] == result["reason"]
    assert entries[0]["status"] == status

    assert captured_notifications == [("0001", result["reason"])]


def test_run_tick_unreadable_status_after_dispatch_is_logged_not_raised(
    tmp_path: Path, captured_notifications: list[tuple[str, str]]
) -> None:
    """The ticket's own state vanishing mid-build — a concurrent `/cancel`,
    `/abandon`, or `/deliver` — would otherwise produce silence, which is the
    one outcome that defeats the point of an unattended watcher."""
    repo, ticket_dir = seed_dispatchable(tmp_path)

    def removing_dispatch(ticket_info: watch.TicketInfo) -> int:
        (ticket_dir / "status.md").unlink()
        return 0

    result = watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=removing_dispatch)

    assert result["needs_attention"] is True
    assert str(result["reason"]).startswith("ticket state unreadable after dispatch:")
    assert len(attention_entries(repo)) == 1
    assert len(captured_notifications) == 1


def test_run_tick_dispatch_launch_failure_is_needs_attention(
    tmp_path: Path, captured_notifications: list[tuple[str, str]]
) -> None:
    """An `OSError` from the launch itself (no `claude` on PATH) is a distinct
    failure from a post-dispatch re-read failure, and carries the launch error
    as its reason."""
    repo, _ = seed_dispatchable(tmp_path)

    def failing_dispatch(ticket_info: watch.TicketInfo) -> int:
        raise FileNotFoundError("claude: command not found")

    result = watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=failing_dispatch)

    assert result["needs_attention"] is True
    assert result["reason"] == result["error"]
    assert "claude" in str(result["reason"])

    entries = attention_entries(repo)
    assert len(entries) == 1
    assert entries[0]["reason"] == result["reason"]
    assert captured_notifications == [("0001", result["reason"])]


def test_run_tick_still_propagates_a_non_os_error(
    tmp_path: Path, captured_notifications: list[tuple[str, str]]
) -> None:
    """Ticket 0078's contract is unchanged: only `OSError` is caught, so a
    genuine bug in the dispatch callable is never absorbed as needs-attention."""
    repo, _ = seed_dispatchable(tmp_path)

    def buggy_dispatch(ticket_info: watch.TicketInfo) -> int:
        raise ValueError("not a subprocess-launch failure")

    with pytest.raises(ValueError):
        watch.run_tick(repo, tmp_path / "log.jsonl", dispatch=buggy_dispatch)

    assert attention_entries(repo) == []
    assert captured_notifications == []


def test_run_tick_classifies_from_disk_not_the_stale_snapshot(
    tmp_path: Path, captured_notifications: list[tuple[str, str]]
) -> None:
    """`find_dispatchable` only ever yields tickets at `solution`, so reading
    the pre-dispatch snapshot would report *every* dispatch as stuck. A ticket
    the dispatch drove to `done` must read as success."""
    repo, ticket_dir = seed_dispatchable(tmp_path)
    candidate = watch.find_dispatchable(repo)[0]
    assert candidate.status == "solution"

    result = watch.run_tick(
        repo, tmp_path / "log.jsonl", dispatch=leaving_status(ticket_dir, "done")
    )
    assert result["needs_attention"] is False


# ---------------------------------------------------------------------------
# cli_status
# ---------------------------------------------------------------------------


def test_cli_status_reports_zero_when_no_log_exists(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    output = watch.cli_status(repo)
    assert "needs_attention: 0" in output
    assert "latest_attention: None" in output


def test_cli_status_keeps_the_preexisting_lines(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    output = watch.cli_status(repo)
    for key in ("running:", "pid:", "last_tick:", "last_dispatch_outcome:"):
        assert key in output


def test_cli_status_counts_entries_and_names_the_latest(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    watch._append_needs_attention(repo, "0001", "first reason", "changes-requested")
    watch._append_needs_attention(repo, "0002", "second reason", "implementing")

    output = watch.cli_status(repo)

    assert "needs_attention: 2" in output
    assert "0002" in output
    assert "second reason" in output


def test_cli_status_tolerates_a_malformed_trailing_line(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    watch._append_needs_attention(repo, "0001", "only good entry", "changes-requested")
    log_path = watch._needs_attention_path(repo)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write('{"ticket": "0002", "reason": "half-writ')

    output = watch.cli_status(repo)

    assert "needs_attention: 1" in output
    assert "only good entry" in output


def test_cli_status_reports_zero_for_an_empty_log(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    log_path = watch._needs_attention_path(repo)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    assert "needs_attention: 0" in watch.cli_status(repo)
