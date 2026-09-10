"""Standalone background watcher: fires `/autopilot` on tickets approved at
Checkpoint 1, decoupled from the `/problem` session that approved them.

See `.tickets/0078-autopilot-approval-watcher/solution.md` for the design.
Discovery is ledger-driven (reuses `ticket.list_tickets`), so a stray or
malformed `.worktrees/*` directory can never surface as a candidate — a
ticket only appears here if a `claim` event named it. The approval gate is a
content-diff check against the ticket's `problem.md`/`requirements.md`/
`solution.md`, not a raw commit-equality check: `approved-commit` is written
by a commit that is necessarily a descendant of the SHA it records, so
`HEAD == approved-commit` could never hold.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import ticket

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

_STATUS_SNAPSHOT_DEFAULTS: dict[str, object] = {
    "running": False,
    "pid": None,
    "last_tick": None,
    "last_dispatch_outcome": None,
}


@dataclass(frozen=True)
class TicketInfo:
    number: str
    slug: str
    full_slug: str
    worktree_dir: Path
    ticket_dir: Path
    status: str
    approved_at: str
    approved_commit: str


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def scan_worktree_tickets(repo: Path) -> list[TicketInfo]:
    """Every locally-worktreed, claimed ticket with a readable `status.md`."""
    offset = ticket._project_offset(repo)
    out: list[TicketInfo] = []
    for record in ticket.list_tickets(repo):
        number, slug = record["number"], record["slug"]
        full_slug = f"{number}-{slug}"
        worktree_dir = repo / ".worktrees" / full_slug
        ticket_dir = ticket._join_ticket_dir(worktree_dir, offset, full_slug)
        status_md = ticket_dir / "status.md"
        if not status_md.is_file():
            continue
        fields = ticket.parse_status(status_md)
        out.append(
            TicketInfo(
                number=number,
                slug=slug,
                full_slug=full_slug,
                worktree_dir=worktree_dir,
                ticket_dir=ticket_dir,
                status=fields.get("status", ""),
                approved_at=fields.get("approved-at", ""),
                approved_commit=fields.get("approved-commit", ""),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Approval gate — fail closed
# ---------------------------------------------------------------------------


def _approval_check(ticket_info: TicketInfo) -> str:
    """Empty string if approved; otherwise the reason it was rejected, so
    the caller can log *why* — never raises: any git failure reads as "not
    approved," matching the fail-closed contract."""
    commit = ticket_info.approved_commit
    if not _SHA_RE.match(commit):
        return "approved-commit is not a valid SHA"
    worktree = ticket_info.worktree_dir
    ancestor = subprocess.run(
        ["git", "-C", str(worktree), "merge-base", "--is-ancestor", commit, "HEAD"],
        capture_output=True,
    )
    if ancestor.returncode != 0:
        return "approved-commit is not an ancestor of the branch's current HEAD"
    try:
        design_paths = [
            str((ticket_info.ticket_dir / name).relative_to(worktree))
            for name in ("problem.md", "requirements.md", "solution.md")
        ]
    except ValueError:
        return "ticket directory is not inside its own worktree"
    diff = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--quiet", commit, "HEAD", "--", *design_paths],
        capture_output=True,
    )
    if diff.returncode != 0:
        return "design files changed since approval (content drift)"
    return ""


def is_approval_valid(ticket_info: TicketInfo) -> bool:
    return _approval_check(ticket_info) == ""


def _log_rejection(repo: Path, number: str, reason: str) -> None:
    log_dir = repo / ".harness" / "autopilot-watch"
    log_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ticket": number, "reason": reason, "ts": time.time()})
    with (log_dir / "rejections.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def find_dispatchable(
    repo: Path, dispatch_log: set[tuple[str, str]] | None = None
) -> list[TicketInfo]:
    dispatched = dispatch_log if dispatch_log is not None else set()
    solution_with_commit = [
        candidate
        for candidate in scan_worktree_tickets(repo)
        if candidate.status == "solution" and candidate.approved_commit
    ]
    approved: list[TicketInfo] = []
    for candidate in solution_with_commit:
        reason = _approval_check(candidate)
        if reason:
            _log_rejection(repo, candidate.number, reason)
            continue
        approved.append(candidate)
    approved = [
        candidate
        for candidate in approved
        if (candidate.number, candidate.approved_commit) not in dispatched
    ]
    return sorted(approved, key=lambda candidate: candidate.number)


# ---------------------------------------------------------------------------
# Dispatch log — commit-keyed, durable
# ---------------------------------------------------------------------------


def load_dispatch_log(log_path: Path) -> set[tuple[str, str]]:
    if not log_path.is_file():
        return set()
    entries: set[tuple[str, str]] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        number, commit = record.get("ticket"), record.get("approved_commit")
        if number and commit:
            entries.add((number, commit))
    return entries


def record_dispatch(log_path: Path, number: str, approved_commit: str) -> None:
    """Append-via-replace: read-modify-write through a temp file, so a
    concurrent reader never observes a half-written line."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
    line = json.dumps({"ticket": number, "approved_commit": approved_commit, "ts": time.time()})
    tmp = log_path.with_name(f"{log_path.name}.tmp-{os.getpid()}")
    tmp.write_text(existing + line + "\n", encoding="utf-8")
    os.replace(tmp, log_path)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def default_dispatch(ticket_info: TicketInfo, repo: Path) -> int:
    log_dir = repo / ".harness" / "autopilot-watch"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{ticket_info.number}.log"
    with log_file.open("a", encoding="utf-8") as handle:
        result = subprocess.run(
            ["claude", "-p", f"/autopilot {ticket_info.number}"],
            cwd=ticket_info.worktree_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    return result.returncode


def run_tick(
    repo: Path,
    log_path: Path,
    dispatch: Callable[[TicketInfo], int] | None = None,
) -> dict[str, object]:
    """At most one dispatch per call, lowest ticket number first. The log
    entry is written *before* `dispatch` runs (FR-6): a killed process still
    leaves the log updated, so a restart never double-dispatches. The
    dispatch's exit code is always returned (never discarded) so `status`
    can distinguish a failed autopilot build from a clean one.

    A dispatch call launches a subprocess; the specific, expected failure
    mode there is `OSError` (e.g. the `claude` binary is missing) — that is
    caught and reported. Anything else is a genuine bug and propagates: the
    CLI `tick` entrypoint then exits non-zero, which the *shell* loop
    (`bin/autopilot-watch start`'s `while true; do tick; sleep N; done`,
    no `set -e`) simply proceeds past — the process boundary, not a broad
    Python catch, is what keeps the watcher's outer loop alive (FR-9)."""
    dispatch_fn = dispatch if dispatch is not None else lambda t: default_dispatch(t, repo)
    candidates = find_dispatchable(repo, load_dispatch_log(log_path))
    if not candidates:
        return {"dispatched": None, "error": None, "exit_code": None}
    target = candidates[0]
    record_dispatch(log_path, target.number, target.approved_commit)
    try:
        exit_code = dispatch_fn(target)
    except OSError as exc:
        return {"dispatched": target.number, "error": str(exc), "exit_code": None}
    return {"dispatched": target.number, "error": None, "exit_code": exit_code}


# ---------------------------------------------------------------------------
# PID lifecycle (mirrors ticket.py's _pid_alive staleness semantics)
# ---------------------------------------------------------------------------


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid_file(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        pid = int(text)
    except ValueError:
        return None
    return pid if pid > 0 else None


def write_pid_file(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(str(pid), encoding="utf-8")
    os.replace(tmp, path)


def remove_pid_file(path: Path) -> None:
    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Status snapshot (what `/autopilot-watch status` reports)
# ---------------------------------------------------------------------------


def read_status_snapshot(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_STATUS_SNAPSHOT_DEFAULTS)
    return {**_STATUS_SNAPSHOT_DEFAULTS, **data}


def write_status_snapshot(
    path: Path,
    *,
    running: bool,
    pid: int | None,
    last_tick: str | None,
    last_dispatch_outcome: str | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "running": running,
        "pid": pid,
        "last_tick": last_tick,
        "last_dispatch_outcome": last_dispatch_outcome,
    }
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# CLI — start / stop / status / tick
# ---------------------------------------------------------------------------


def _state_paths(repo: Path) -> tuple[Path, Path, Path]:
    state_dir = repo / ".harness" / "autopilot-watch"
    return (state_dir / "watch.pid", state_dir / "dispatch-log.jsonl", state_dir / "status.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Interrupted(Exception):
    """Raised from the SIGTERM handler installed in `cli_tick` — never a
    normal control-flow exception, so it is never mistaken for a dispatch
    failure by `run_tick`'s own `except OSError`."""


def _outcome_label(result: dict[str, object]) -> str:
    if result["dispatched"] is None:
        return "no-op"
    if result["error"]:
        return f"dispatched {result['dispatched']} (error: {result['error']})"
    return f"dispatched {result['dispatched']} (exit {result['exit_code']})"


def cli_tick(repo: Path) -> int:
    """Run exactly one tick and record it. A SIGTERM received while blocked
    on the dispatch subprocess (i.e. `stop` was called mid-dispatch) is
    caught long enough to record "interrupted" before this process exits —
    the *shell* loop that repeatedly invokes this as a fresh subprocess (see
    `cli_start`) is otherwise what survives a tick that raises or is killed
    outright (FR-9); this handler only covers the one case that needs a
    recorded outcome rather than silence."""
    _, log_path, status_path = _state_paths(repo)

    def _on_terminate(signum: int, frame: object) -> None:
        write_status_snapshot(
            status_path, running=False, pid=os.getpid(), last_tick=_now_iso(), last_dispatch_outcome="interrupted"
        )
        raise _Interrupted()

    previous_handler = signal.signal(signal.SIGTERM, _on_terminate)
    try:
        result = run_tick(repo, log_path)
    except _Interrupted:
        return 143
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    write_status_snapshot(
        status_path, running=True, pid=os.getpid(), last_tick=_now_iso(), last_dispatch_outcome=_outcome_label(result)
    )
    return 0


_LOOP_SCRIPT = 'while true; do "$1" "$2" tick "$3"; sleep "$4"; done'


def cli_start(repo: Path, interval: int = 30) -> int:
    pid_path, _, _ = _state_paths(repo)
    existing = read_pid_file(pid_path)
    if existing is not None and pid_is_alive(existing):
        print(f"autopilot-watch: already running (pid {existing})")
        return 1
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    loop_log = (pid_path.parent / "loop.log").open("a", encoding="utf-8")
    proc = subprocess.Popen(
        ["/bin/sh", "-c", _LOOP_SCRIPT, "sh", sys.executable, str(Path(__file__).resolve()), str(repo), str(interval)],
        stdout=loop_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    write_pid_file(pid_path, proc.pid)
    print(f"autopilot-watch: started (pid {proc.pid}, interval {interval}s)")
    return 0


def cli_stop(repo: Path, grace_seconds: float = 10.0) -> int:
    pid_path, _, _ = _state_paths(repo)
    pid = read_pid_file(pid_path)
    if pid is None or not pid_is_alive(pid):
        remove_pid_file(pid_path)
        print("autopilot-watch: not running")
        return 0
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and pid_is_alive(pid):
        time.sleep(0.1)
    if pid_is_alive(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    remove_pid_file(pid_path)
    print("autopilot-watch: stopped")
    return 0


def cli_status(repo: Path) -> str:
    pid_path, _, status_path = _state_paths(repo)
    pid = read_pid_file(pid_path)
    running = pid is not None and pid_is_alive(pid)
    snapshot = read_status_snapshot(status_path)
    return "\n".join(
        [
            f"running: {running}",
            f"pid: {pid if running else None}",
            f"last_tick: {snapshot['last_tick']}",
            f"last_dispatch_outcome: {snapshot['last_dispatch_outcome']}",
        ]
    )


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: autopilot_watch.py <start|stop|status|tick> <repo> [--interval N]", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    positional = [arg for arg in rest if not arg.startswith("--")]
    if cmd == "tick":
        if not positional:
            print("usage: autopilot_watch.py tick <repo>", file=sys.stderr)
            return 2
        return cli_tick(Path(positional[0]))
    if cmd == "start":
        if not positional:
            print("usage: autopilot_watch.py start <repo> [--interval N]", file=sys.stderr)
            return 2
        interval = 30
        if "--interval" in rest:
            interval = int(rest[rest.index("--interval") + 1])
        return cli_start(Path(positional[0]), interval=interval)
    if cmd == "stop":
        if not positional:
            print("usage: autopilot_watch.py stop <repo>", file=sys.stderr)
            return 2
        return cli_stop(Path(positional[0]))
    if cmd == "status":
        if not positional:
            print("usage: autopilot_watch.py status <repo>", file=sys.stderr)
            return 2
        print(cli_status(Path(positional[0])))
        return 0
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
