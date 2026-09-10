"""Unit + integration tests for autopilot_watch.py's CLI (start/stop/status/tick)
and the bin/autopilot-watch shim (ticket 0078).

`start` launches a *shell* loop (`while true; do ... tick ...; sleep N; done`,
own process group, no `set -e`) rather than looping inside a long-lived Python
process — a tick that raises simply exits that one iteration's subprocess
non-zero, and the shell loop proceeds regardless. That process boundary, not a
broad Python `except`, is what keeps the watcher alive across a bad tick
(the repo's code-gen rules block a bare/broad `except Exception`).
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

import autopilot_watch as watch

_MODULE_PATH = str(Path(watch.__file__).resolve())
_BIN_SHIM = Path(__file__).resolve().parent.parent / "bin" / "autopilot-watch"


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


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------------------------------------------------------------------------
# bin/autopilot-watch shim
# ---------------------------------------------------------------------------


def test_bin_shim_is_thin_forwarder() -> None:
    text = _BIN_SHIM.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "#!/usr/bin/env bash"
    assert "autopilot_watch.py" in text
    assert len([line for line in text.splitlines() if line.strip()]) <= 2


def test_bin_shim_is_executable() -> None:
    mode = _BIN_SHIM.stat().st_mode
    assert mode & stat.S_IXUSR


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------


def test_cli_tick_writes_status_snapshot_no_op(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    watch.cli_tick(repo)
    _, _, status_path = watch._state_paths(repo)
    snapshot = watch.read_status_snapshot(status_path)
    assert snapshot["last_tick"] is not None
    assert snapshot["last_dispatch_outcome"] == "no-op"


# ---------------------------------------------------------------------------
# start / stop / status — no real dispatch
# ---------------------------------------------------------------------------


def test_start_refuses_second_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _init_repo(tmp_path)
    pid_path, _, _ = watch._state_paths(repo)
    watch.write_pid_file(pid_path, os.getpid())  # this test process is definitely alive

    called = {"popen": False}

    def _fail_if_called(*args, **kwargs):
        called["popen"] = True
        raise AssertionError("start must not spawn a second loop")

    monkeypatch.setattr(watch.subprocess, "Popen", _fail_if_called)
    result = watch.cli_start(repo, interval=30)
    assert result != 0
    assert called["popen"] is False


def test_stop_when_not_running_is_noop(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    pid_path, _, _ = watch._state_paths(repo)
    assert watch.cli_stop(repo) == 0
    assert not pid_path.exists()


def test_stop_removes_stale_pid_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    pid_path, _, _ = watch._state_paths(repo)
    proc = subprocess.Popen(["true"])
    proc.wait()
    watch.write_pid_file(pid_path, proc.pid)  # definitely dead now
    assert watch.cli_stop(repo) == 0
    assert not pid_path.exists()


def test_status_reports_not_running_on_fresh_repo(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    output = watch.cli_status(repo)
    assert "running: False" in output


# ---------------------------------------------------------------------------
# start / stop — real detached loop (integration)
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, _MODULE_PATH, *args], capture_output=True, text=True, check=False
    )


def test_start_then_stop_real_loop(tmp_path: Path) -> None:
    """`start` and `stop` are exercised as two *separate* CLI invocations
    (as they are in real use via bin/autopilot-watch) — the loop process is
    orphaned from its launching process and re-parented to init, which is
    what actually reaps it. Calling cli_start()/cli_stop() as plain Python
    functions within one long-lived process (this test's own) would instead
    leave the loop a zombie forever, since pid_is_alive can't distinguish
    "zombie" from "alive" without being the reaping parent — an inherent
    POSIX limitation `ticket.py`'s own `_pid_alive` shares."""
    repo = _init_repo(tmp_path)
    pid_path, _, status_path = watch._state_paths(repo)

    start = _run_cli("start", str(repo), "--interval", "1")
    assert start.returncode == 0, start.stderr
    pid = watch.read_pid_file(pid_path)
    assert pid is not None
    try:
        assert _wait_until(lambda: watch.pid_is_alive(pid)), "loop did not start"
        assert _wait_until(
            lambda: watch.read_status_snapshot(status_path)["last_tick"] is not None,
            timeout=5.0,
        ), "loop never ran a tick"
    finally:
        stop = _run_cli("stop", str(repo))
        assert stop.returncode == 0, stop.stderr

    assert _wait_until(lambda: not watch.pid_is_alive(pid)), "loop still alive after stop"
    assert not pid_path.exists()


def test_stop_mid_dispatch_terminates_child_and_keeps_log_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ticket is approved and dispatchable; the loop's tick shells out to a
    fake `claude` that blocks. `stop` must terminate that blocked child within
    its grace period, and the dispatch-log entry (written before dispatch)
    must survive — no rollback, no auto-retry, matching FR-7."""
    from tests.test_0078_autopilot_watch_core import (  # local import: reuse fixtures
        _approve,
        _base_fields,
        _head,
        _seed_claim,
        _seed_ticket_branch_and_worktree,
    )

    repo = _init_repo(tmp_path)
    _seed_claim(repo, 1, "foo")
    worktree, ticket_dir = _seed_ticket_branch_and_worktree(repo, 1, "foo", _base_fields(1, "foo"))
    sha = _head(worktree)
    _approve(worktree, ticket_dir, sha)

    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    marker = tmp_path / "claude-started"
    fake_claude = fake_bin / "claude"
    fake_claude.write_text(
        "#!/usr/bin/env bash\n"
        f"echo started > {marker}\n"
        "sleep 60\n",
        encoding="utf-8",
    )
    fake_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    pid_path, log_path, _ = watch._state_paths(repo)
    start = subprocess.run(
        [sys.executable, _MODULE_PATH, "start", str(repo), "--interval", "1"],
        capture_output=True, text=True, check=False, env=dict(os.environ),
    )
    try:
        assert start.returncode == 0, start.stderr
        assert _wait_until(lambda: marker.exists(), timeout=10.0), "fake claude never started"
        assert ("0001", sha) in watch.load_dispatch_log(log_path)
    finally:
        stop_started = time.monotonic()
        stop = subprocess.run(
            [sys.executable, _MODULE_PATH, "stop", str(repo)],
            capture_output=True, text=True, check=False,
        )
        assert stop.returncode == 0, stop.stderr
        assert time.monotonic() - stop_started < 8.0

    # the dispatch log entry is not rolled back by a terminated dispatch
    assert ("0001", sha) in watch.load_dispatch_log(log_path)
