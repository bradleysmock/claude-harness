# harness-combined/tests/test_0056_ticket_lock.py
"""Tests for the 0056 ticket-lock move: `.tickets/.ticket.lock` acquire, steal,
heartbeat, and release now live inside `ticket.py`'s `claim()` rather than
being hand-run as Bash in `commands/problem.md` Phase 1.

No wall-clock sleeps: `time.time`, `time.sleep`, and `os.kill` are monkeypatched
throughout rather than exercised for real (NFR-3).
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

import ticket

_REPO_ROOT = Path(__file__).parent.parent
_GUARD_SPEC = importlib.util.spec_from_file_location(
    "ticket_commit_guard", _REPO_ROOT / "hooks" / "ticket_commit_guard.py"
)
assert _GUARD_SPEC and _GUARD_SPEC.loader
guard = importlib.util.module_from_spec(_GUARD_SPEC)
_GUARD_SPEC.loader.exec_module(guard)

# ── fixtures ────────────────────────────────────────────────────────────────

def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    (repo / ".tickets").mkdir()
    (repo / ".tickets" / ".keep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


def _lock(tickets_root: Path) -> Path:
    return tickets_root / ".ticket.lock"


def _write_lock(tickets_root: Path, pid: int, epoch: int) -> Path:
    lock = _lock(tickets_root)
    lock.write_text(f"{pid}:{epoch}", encoding="utf-8")
    return lock


class _FakeTime:
    """A monotonically-advancing fake clock with a no-op sleep, so no test
    depends on a real wall-clock second."""

    def __init__(self, start: int = 1_000_000) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def time(self) -> float:
        return float(self.now)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += int(seconds)


def _alive_kill(pid: int, sig: int) -> None:
    return None  # process is alive — os.kill(pid, 0) succeeds


def _dead_kill(pid: int, sig: int) -> None:
    raise ProcessLookupError(pid)


# ── _parse_lock_content ─────────────────────────────────────────────────────

def test_parse_lock_content_valid() -> None:
    assert ticket._parse_lock_content("123:456") == (123, 456)


@pytest.mark.parametrize("raw", ["0:123", "-5:123", "abc:123", "5:xyz", "5", ""])
def test_parse_lock_content_malformed(raw: str) -> None:
    assert ticket._parse_lock_content(raw) is None


# ── _pid_alive ───────────────────────────────────────────────────────────────

def test_pid_alive_process_lookup_error_is_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ticket.os, "kill", _dead_kill)
    assert ticket._pid_alive(999) is False


def test_pid_alive_permission_error_is_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_permission(pid: int, sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(ticket.os, "kill", _raise_permission)
    assert ticket._pid_alive(1) is True


def test_pid_alive_success_is_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ticket.os, "kill", _alive_kill)
    assert ticket._pid_alive(123) is True


# ── _lock_is_stale ───────────────────────────────────────────────────────────

def test_lock_is_stale_by_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    monkeypatch.setattr(ticket.os, "kill", _alive_kill)
    parsed = (123, 1_000_000 - ticket._LOCK_STALE_SECONDS - 1)
    assert ticket._lock_is_stale(parsed) is True


def test_lock_is_stale_by_dead_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    monkeypatch.setattr(ticket.os, "kill", _dead_kill)
    assert ticket._lock_is_stale((999, 1_000_000)) is True


def test_lock_is_fresh_and_alive_is_not_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    monkeypatch.setattr(ticket.os, "kill", _alive_kill)
    assert ticket._lock_is_stale((123, 1_000_000)) is False


# ── _lock_capture (rename-verify primitive) ─────────────────────────────────

def test_lock_capture_match_removes_temp_and_returns_true(tmp_path: Path) -> None:
    lock = tmp_path / ".ticket.lock"
    lock.write_text("111:2000", encoding="utf-8")
    assert ticket._lock_capture(lock, "111:2000") is True
    assert not lock.exists()
    assert list(tmp_path.glob(".ticket.lock.stale-*")) == []


def test_lock_capture_mismatch_restores_lock_non_clobberingly(tmp_path: Path) -> None:
    lock = tmp_path / ".ticket.lock"
    lock.write_text("999:9999", encoding="utf-8")  # a fresh lock, recreated after observation
    result = ticket._lock_capture(lock, "111:2000")  # stale content we originally observed
    assert result is False
    assert lock.read_text(encoding="utf-8") == "999:9999"
    assert list(tmp_path.glob(".ticket.lock.stale-*")) == []


def test_lock_capture_mismatch_with_file_exists_error_just_unlinks_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / ".ticket.lock"
    lock.write_text("999:9999", encoding="utf-8")

    def _raise_exists(src, dst):
        raise FileExistsError

    monkeypatch.setattr(ticket.os, "link", _raise_exists)
    result = ticket._lock_capture(lock, "111:2000")
    assert result is False
    assert not lock.exists()  # a third process's lock — we don't clobber or restore
    assert list(tmp_path.glob(".ticket.lock.stale-*")) == []


def test_lock_capture_vanished_at_rename_returns_false(tmp_path: Path) -> None:
    lock = tmp_path / ".ticket.lock"  # never created
    assert ticket._lock_capture(lock, "111:2000") is False


def test_lock_capture_vanished_at_reread_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / ".ticket.lock"
    lock.write_text("111:2000", encoding="utf-8")
    real_rename = ticket.os.rename

    def _rename_then_vanish(src, dst):
        real_rename(src, dst)
        Path(dst).unlink()  # the temp disappears before it can be re-read

    monkeypatch.setattr(ticket.os, "rename", _rename_then_vanish)
    assert ticket._lock_capture(lock, "111:2000") is False


# ── _release_ticket_lock ─────────────────────────────────────────────────────

def test_release_missing_lock_is_noop(tmp_path: Path) -> None:
    ticket._release_ticket_lock(tmp_path)  # must not raise


def test_release_own_lock_removes_it(tmp_path: Path) -> None:
    _write_lock(tmp_path, ticket.os.getpid(), 1000)
    ticket._release_ticket_lock(tmp_path)
    assert not _lock(tmp_path).exists()


def test_release_foreign_lock_leaves_it_untouched(tmp_path: Path) -> None:
    _write_lock(tmp_path, ticket.os.getpid() + 1, 1000)
    ticket._release_ticket_lock(tmp_path)
    assert _lock(tmp_path).read_text(encoding="utf-8") == f"{ticket.os.getpid() + 1}:1000"


# ── _heartbeat_ticket_lock ───────────────────────────────────────────────────

def test_heartbeat_own_lock_rewrites_epoch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeTime(start=5000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    own = ticket.os.getpid()
    _write_lock(tmp_path, own, 1)
    assert ticket._heartbeat_ticket_lock(tmp_path) is True
    assert _lock(tmp_path).read_text(encoding="utf-8") == f"{own}:5000"


def test_heartbeat_foreign_pid_stops_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    foreign = ticket.os.getpid() + 1
    _write_lock(tmp_path, foreign, 1)
    assert ticket._heartbeat_ticket_lock(tmp_path) is False
    assert _lock(tmp_path).read_text(encoding="utf-8") == f"{foreign}:1"  # untouched
    assert "no longer owned" in capsys.readouterr().err


def test_heartbeat_missing_lock_stops_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ticket._heartbeat_ticket_lock(tmp_path) is False
    assert "vanished" in capsys.readouterr().err


# ── _reap_stale_lock_temps ───────────────────────────────────────────────────

def test_reap_dead_filename_and_dead_content_pid_unlinks_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ticket.os, "kill", _dead_kill)
    temp = tmp_path / ".ticket.lock.stale-424242"
    temp.write_text("999999:1", encoding="utf-8")
    ticket._reap_stale_lock_temps(tmp_path, _lock(tmp_path))
    assert not temp.exists()
    assert not _lock(tmp_path).exists()


def test_reap_dead_filename_alive_content_restores_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_content_pid = 55
    filename_pid = 424242

    def _kill(pid: int, sig: int) -> None:
        if pid == filename_pid:
            raise ProcessLookupError(pid)
        # content pid is alive

    monkeypatch.setattr(ticket.os, "kill", _kill)
    temp = tmp_path / f".ticket.lock.stale-{filename_pid}"
    temp.write_text(f"{live_content_pid}:1", encoding="utf-8")
    ticket._reap_stale_lock_temps(tmp_path, _lock(tmp_path))
    assert not temp.exists()
    assert _lock(tmp_path).read_text(encoding="utf-8") == f"{live_content_pid}:1"


def test_reap_alive_filename_pid_left_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ticket.os, "kill", _alive_kill)
    temp = tmp_path / ".ticket.lock.stale-777"
    temp.write_text("777:1", encoding="utf-8")
    ticket._reap_stale_lock_temps(tmp_path, _lock(tmp_path))
    assert temp.exists()  # still owned by a running process — left alone


# ── _acquire_ticket_lock ─────────────────────────────────────────────────────

def test_acquire_fresh_lock_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeTime(start=42)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    ticket._acquire_ticket_lock(tmp_path)
    assert _lock(tmp_path).read_text(encoding="utf-8") == f"{ticket.os.getpid()}:42"


def test_acquire_steals_stale_epoch_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    monkeypatch.setattr(ticket.time, "sleep", clock.sleep)
    monkeypatch.setattr(ticket.os, "kill", _alive_kill)  # holder pid alive, but epoch is stale
    _write_lock(tmp_path, 424242, 1_000_000 - ticket._LOCK_STALE_SECONDS - 1)
    ticket._acquire_ticket_lock(tmp_path)
    assert _lock(tmp_path).read_text(encoding="utf-8") == f"{ticket.os.getpid()}:1000000"
    assert clock.sleeps == []  # stolen immediately, no live-retry wait


def test_acquire_steals_dead_pid_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    monkeypatch.setattr(ticket.os, "kill", _dead_kill)
    _write_lock(tmp_path, 424242, 1_000_000)  # fresh epoch, but the pid is dead
    ticket._acquire_ticket_lock(tmp_path)
    assert _lock(tmp_path).read_text(encoding="utf-8") == f"{ticket.os.getpid()}:1000000"


def test_acquire_malformed_lock_is_steal_eligible_without_calling_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)

    def _fail_if_called(pid: int, sig: int) -> None:
        raise AssertionError("os.kill must never be called on malformed lock content")

    monkeypatch.setattr(ticket.os, "kill", _fail_if_called)
    _write_lock(tmp_path, 0, 1_000_000)  # pid <= 0 — malformed, never os.kill'ed
    ticket._acquire_ticket_lock(tmp_path)
    assert _lock(tmp_path).read_text(encoding="utf-8") == f"{ticket.os.getpid()}:1000000"


def test_acquire_live_lock_retries_five_times_then_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    monkeypatch.setattr(ticket.time, "sleep", clock.sleep)
    monkeypatch.setattr(ticket.os, "kill", _alive_kill)
    _write_lock(tmp_path, 424242, 1_000_000)  # fresh epoch, alive pid — always live
    with pytest.raises(RuntimeError, match="424242"):
        ticket._acquire_ticket_lock(tmp_path)
    assert clock.sleeps == [ticket._LOCK_SLEEP_SECONDS] * ticket._LOCK_LIVE_RETRIES


def test_acquire_unparseable_holder_names_unknown_holder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    monkeypatch.setattr(ticket.time, "sleep", clock.sleep)
    # Malformed content is always steal-eligible; a persistent rename-verify
    # race (mocked False every round) exhausts the live-retry cap with the
    # last observation still unparseable.
    monkeypatch.setattr(ticket, "_lock_capture", lambda lock, expected: False)
    _write_lock(tmp_path, 0, 1_000_000)  # pid <= 0 — malformed
    with pytest.raises(RuntimeError, match="unknown holder") as exc_info:
        ticket._acquire_ticket_lock(tmp_path)
    assert "0:1000000" in str(exc_info.value)


def test_acquire_ceiling_raises_on_adversarial_re_steal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    monkeypatch.setattr(ticket.time, "sleep", clock.sleep)
    _write_lock(tmp_path, 0, 1_000_000)  # malformed — always steal-eligible
    # `_lock_capture` "succeeds" every round but never actually removes the
    # lock file, so `os.open(O_EXCL)` keeps failing — an adversarial re-steal.
    monkeypatch.setattr(ticket, "_lock_capture", lambda lock, expected: True)
    with pytest.raises(RuntimeError):
        ticket._acquire_ticket_lock(tmp_path)
    assert clock.sleeps == []  # every round stole "successfully" — no live wait


def test_two_interleaved_acquisitions_never_both_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _FakeTime(start=1_000_000)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    ticket._acquire_ticket_lock(tmp_path)  # first acquirer holds it
    first_holder = _lock(tmp_path).read_text(encoding="utf-8")

    monkeypatch.setattr(ticket.time, "sleep", clock.sleep)
    monkeypatch.setattr(ticket.os, "kill", _alive_kill)  # first holder looks alive to the second
    with pytest.raises(RuntimeError):
        ticket._acquire_ticket_lock(tmp_path)  # second acquirer must not also succeed
    assert _lock(tmp_path).read_text(encoding="utf-8") == first_holder  # unchanged


# ── claim() integration ──────────────────────────────────────────────────────

def test_claim_lock_absent_after_success(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ticket.claim(repo, "widget", "Widget")
    assert not (repo / ".tickets" / ".ticket.lock").exists()


def test_claim_no_contention_git_behavior_unchanged(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    slug = ticket.claim(repo, "widget", "Widget")
    assert slug == "0001-widget"
    assert any(r["event"] == "claim" and r["number"] == 1 for r in ticket.ledger_read(repo))
    assert (repo / ".worktrees" / slug).is_dir()
    assert not (repo / ".tickets" / slug).exists()  # no `main` commit


def test_claim_lock_released_and_exception_propagates_on_forced_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)

    def _boom(repo_, build, *, push, max_retries):
        raise RuntimeError("boom")

    monkeypatch.setattr(ticket, "ledger_append", _boom)
    with pytest.raises(RuntimeError, match="boom"):
        ticket.claim(repo, "widget", "Widget")
    assert not (repo / ".tickets" / ".ticket.lock").exists()  # released despite the raise


def test_claim_heartbeats_each_renumber_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)
    clock = _FakeTime(start=100)
    monkeypatch.setattr(ticket.time, "time", clock.time)
    seen_epochs: list[str] = []

    def _fake_ledger_append(repo_, build, *, push, max_retries):
        result = None
        for _ in range(3):  # simulate 3 renumber/retry iterations
            clock.now += 10
            _, result = build([])
            seen_epochs.append((repo_ / ".tickets" / ".ticket.lock").read_text(encoding="utf-8"))
        return result

    monkeypatch.setattr(ticket, "ledger_append", _fake_ledger_append)
    ticket.claim(repo, "widget", "Widget")
    own = ticket.os.getpid()
    assert seen_epochs == [f"{own}:110", f"{own}:120", f"{own}:130"]


def test_claim_lost_ownership_mid_build_raises_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Fail-closed: in a local-only repo the ledger's `update-ref` has no
    # compare-and-swap, so a claim event built after ownership is lost could
    # race a concurrent successor's own claim. `build()` must abort instead of
    # returning the event.
    repo = _init_repo(tmp_path)
    successor_pid = ticket.os.getpid() + 1
    reached_return = False

    def _fake_ledger_append(repo_, build, *, push, max_retries):
        nonlocal reached_return
        # A successor steals the lock before this iteration's heartbeat runs.
        (repo_ / ".tickets" / ".ticket.lock").write_text(f"{successor_pid}:1", encoding="utf-8")
        build([])  # must raise — must not reach the line below
        reached_return = True
        return None

    monkeypatch.setattr(ticket, "ledger_append", _fake_ledger_append)
    with pytest.raises(ticket._LockOwnershipLost):
        ticket.claim(repo, "widget", "Widget")
    assert reached_return is False
    # the successor's lock must survive claim()'s finally untouched
    assert (repo / ".tickets" / ".ticket.lock").read_text(encoding="utf-8") == f"{successor_pid}:1"
    assert "no longer owned" in capsys.readouterr().err


def test_claim_lost_ownership_writes_nothing_to_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(ticket, "_heartbeat_ticket_lock", lambda tickets_root: False)
    with pytest.raises(ticket._LockOwnershipLost):
        ticket.claim(repo, "widget", "Widget")
    assert ticket.ledger_read(repo) == []
    assert not (repo / ".worktrees" / "0001-widget").exists()


# ── commands/problem.md Phase 1 (content-verification) ─────────────────────

def _problem_phase_1() -> str:
    text = (_REPO_ROOT / "commands" / "problem.md").read_text(encoding="utf-8")
    start = text.index("## Phase 1")
    end = text.index("## Phase 1.5")
    return text[start:end]


def test_problem_phase_1_has_no_manual_lock_bash() -> None:
    phase_1 = _problem_phase_1()
    assert "rm -f .tickets/.ticket.lock" not in phase_1
    assert "Acquire the local lock" not in phase_1


def test_problem_phase_1_runs_single_claim_call() -> None:
    phase_1 = _problem_phase_1()
    assert '${CLAUDE_PLUGIN_ROOT}/ticket.py" claim <slug> "<title>" --push' in phase_1
    assert "acquires" in phase_1 and "itself" in phase_1  # built-in-lock note


# ── hooks/ticket_commit_guard.py IGNORED_STALE_PREFIX ───────────────────────

def _repo_for_guard(tmp_path: Path) -> Path:
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


def test_guard_ignores_lock_stale_temp(tmp_path: Path) -> None:
    repo = _repo_for_guard(tmp_path)
    (repo / ".tickets" / ".ticket.lock.stale-12345").write_text("1:1", encoding="utf-8")
    assert guard.dirty_ticket_files(repo) == []


def test_guard_still_ignores_lock_and_active(tmp_path: Path) -> None:
    repo = _repo_for_guard(tmp_path)
    (repo / ".tickets" / ".ticket.lock").write_text("1:1", encoding="utf-8")
    (repo / ".tickets" / ".active").write_text("0001-x", encoding="utf-8")
    assert guard.dirty_ticket_files(repo) == []


def test_guard_does_not_ignore_unrelated_stale_substring(tmp_path: Path) -> None:
    repo = _repo_for_guard(tmp_path)
    (repo / ".tickets" / "stale-report.md").write_text("x", encoding="utf-8")
    assert any("stale-report.md" in f for f in guard.dirty_ticket_files(repo))


# ── context/harness-reference.md lock line ──────────────────────────────────

def test_harness_reference_lock_line_notes_claim_manages_it() -> None:
    text = (_REPO_ROOT / "context" / "harness-reference.md").read_text(encoding="utf-8")
    lock_line = next(line for line in text.splitlines() if ".ticket.lock " in line)
    assert "claim()" in lock_line
    assert "pid:epoch" in lock_line
