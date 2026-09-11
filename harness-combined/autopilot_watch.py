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


@dataclass(frozen=True)
class ClassifyResult:
    """How a finished dispatch read: success, or needs the lead's attention.

    `reason` is None exactly when `needs_attention` is False — a needs-attention
    outcome always carries the text that goes in the log and the notification.
    """

    needs_attention: bool
    reason: str | None


# ---------------------------------------------------------------------------
# State paths
# ---------------------------------------------------------------------------


def _state_dir(repo: Path) -> Path:
    """The one directory every piece of watcher state lives in.

    Derived in one place so the rejection log, the per-ticket dispatch logs,
    the pid/dispatch-log/status trio, and the needs-attention log cannot drift
    apart — `cli_status` has to read the same file `run_tick` appends to.
    """
    return repo / ".harness" / "autopilot-watch"


def _needs_attention_path(repo: Path) -> Path:
    return _state_dir(repo) / "needs-attention.jsonl"


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
    ancestor_check = subprocess.run(
        ["git", "-C", str(worktree), "merge-base", "--is-ancestor", commit, "HEAD"],
        capture_output=True,
    )
    if ancestor_check.returncode != 0:
        return "approved-commit is not an ancestor of the branch's current HEAD"
    try:
        design_paths = [
            str((ticket_info.ticket_dir / name).relative_to(worktree))
            for name in ("problem.md", "requirements.md", "solution.md")
        ]
    except ValueError:
        return "ticket directory is not inside its own worktree"
    diff_check = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--quiet", commit, "HEAD", "--", *design_paths],
        capture_output=True,
    )
    if diff_check.returncode != 0:
        return "design files changed since approval (content drift)"
    return ""


def _log_rejection(repo: Path, number: str, reason: str) -> None:
    log_dir = _state_dir(repo)
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
# Needs-attention classification, log, and notification
# ---------------------------------------------------------------------------

#: The only post-dispatch status that means the ticket is finished and needs
#: nothing from the lead. Everything else — `changes-requested`, an unmoved
#: `solution`, a build stuck at `implementing`/`review-ready` — is an outcome
#: someone has to look at.
_SUCCESS_STATUS = "done"

#: The reason text reaches `osascript` through the environment, so these names
#: are the only thing the AppleScript source below has to name. Read inside the
#: script with `system attribute`, which is why the reason is never a CLI token
#: and never AppleScript syntax.
_NOTIFY_TITLE_ENV = "HARNESS_WATCH_NOTIFY_TITLE"
_NOTIFY_BODY_ENV = "HARNESS_WATCH_NOTIFY_BODY"

#: A notifier that hangs must not hold the tick open; the shell loop's next
#: iteration is cheap, a wedged `osascript` is not.
_NOTIFY_TIMEOUT_SECONDS = 10

_NOTIFY_APPLESCRIPT = (
    f'display notification (system attribute "{_NOTIFY_BODY_ENV}") '
    f'with title (system attribute "{_NOTIFY_TITLE_ENV}")'
)


def _read_status_field(ticket_dir: Path) -> tuple[str, str | None]:
    """The ticket's current `status:` value, and why it could not be read.

    The read is split out from the classification below so the file is touched
    exactly once per dispatch: `run_tick` needs both the verdict *and* the
    observed status (for the log entry), and reading twice would let the two
    disagree if the status moved in between.

    Returns `(status, None)` on a successful read — where `status` is `""` for a
    `status.md` carrying no `status:` field, matching `scan_worktree_tickets`'s
    `fields.get("status", "")`. Returns `("", detail)` when the read raised.
    """
    try:
        fields = ticket.parse_status(ticket_dir / "status.md")
    except OSError as exc:
        return "", str(exc)
    return fields.get("status", ""), None


def _classify_status(status: str, read_error: str | None) -> ClassifyResult:
    """Pure verdict over an already-read status — no I/O, no clock, no repo.

    An empty status is ordinary control flow and takes the unrecognized-status
    reason; only a failed *read* takes the separate "unreadable" reason. Silence
    is the one outcome that would defeat an unattended watcher, so everything
    that is not `done` lands on needs-attention.
    """
    if read_error is not None:
        return ClassifyResult(
            needs_attention=True,
            reason=f"ticket state unreadable after dispatch: {read_error}",
        )
    if status == _SUCCESS_STATUS:
        return ClassifyResult(needs_attention=False, reason=None)
    return ClassifyResult(
        needs_attention=True, reason=f"unrecognized post-dispatch status: '{status}'"
    )


def _classify_outcome(ticket_info: TicketInfo) -> ClassifyResult:
    """Re-read the ticket's `status.md` and decide whether the lead is needed.

    Deliberately re-reads from disk rather than trusting `ticket_info.status`:
    that field is the pre-dispatch snapshot, and since `find_dispatchable` only
    ever yields tickets at `solution`, trusting it would report every dispatch
    as stuck. Classification uses only that file — never the per-ticket log or
    the dispatch's stdout — so the signal stays structural instead of depending
    on prose the autopilot flow is free to reword.

    Never raises: the read failure is captured as a value, not an exception. A
    ticket removed mid-build by a concurrent `/cancel`, `/abandon`, or
    `/deliver` therefore surfaces as an alert rather than a crash.
    """
    status, read_error = _read_status_field(ticket_info.ticket_dir)
    return _classify_status(status, read_error)


def _append_needs_attention(repo: Path, number: str, reason: str, status: str) -> None:
    """Append one durable JSON line about an outcome the lead has to look at.

    A plain `open(..., "a")` write, matching `_log_rejection` rather than
    `record_dispatch`'s temp-file replace: this log is pure append — nothing
    ever reads it to decide what to write next — so a single small write is
    atomic under POSIX and the read-modify-write dance would buy nothing.
    """
    log_path = _needs_attention_path(repo)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"ticket": number, "reason": reason, "status": status, "ts": time.time()}
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _load_needs_attention(log_path: Path) -> list[dict[str, object]]:
    """Every well-formed entry, in append order.

    Skips a line that fails to parse instead of raising — `cli_tick` can be
    appending while `cli_status` reads, so a half-written trailing line is
    expected, exactly as `load_dispatch_log` already assumes.
    """
    if not log_path.is_file():
        return []
    entries: list[dict[str, object]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            entries.append(record)
    return entries


def _notify_desktop(number: str, reason: str) -> None:
    """Best-effort desktop notification: `osascript`, then `notify-send`.

    Returns None in every case and never raises — a missing notifier, a
    non-zero exit, or a hang must degrade to log-only, never take down the
    tick. The first notifier that runs to completion wins: `osascript`
    resolving means this is macOS, so a failure there is a failed attempt
    rather than a cue to try the Linux tool.

    The reason travels in the environment, never in `osascript`'s argv. `-e`
    parses its argument as AppleScript *source*, so an embedded quote could
    close the string early and append further AppleScript — `do shell script`
    included. Passing it positionally (`on run argv`) only relocates the
    hazard, because `osascript` documents no `--` end-of-options guarantee and
    a reason beginning with `-` could be taken for another option. An
    environment variable is neither source text nor a CLI token, closing both
    paths at once. `notify-send` has no env-var equivalent for its body, but it
    parses options with GLib's `GOptionContext`, which *does* document `--` as
    ending option parsing — hence the explicit separator there.
    """
    title = f"autopilot-watch: {number} needs attention"
    notify_env = {**os.environ, _NOTIFY_TITLE_ENV: title, _NOTIFY_BODY_ENV: reason}
    attempts = (
        ["osascript", "-e", _NOTIFY_APPLESCRIPT],
        ["notify-send", "--", title, reason],
    )
    for args in attempts:
        try:
            subprocess.run(
                args,
                env=notify_env,
                capture_output=True,
                timeout=_NOTIFY_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def default_dispatch(ticket_info: TicketInfo, repo: Path) -> int:
    log_dir = _state_dir(repo)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{ticket_info.number}.log"
    with log_file.open("a", encoding="utf-8") as handle:
        result = subprocess.run(
            ["claude", "-p", f"/harness-combined:autopilot {ticket_info.number}"],
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
        return {
            "dispatched": None,
            "error": None,
            "exit_code": None,
            "needs_attention": False,
            "reason": None,
        }
    target = candidates[0]
    record_dispatch(log_path, target.number, target.approved_commit)
    try:
        exit_code = dispatch_fn(target)
    except OSError as exc:
        # A launch failure, distinct from the post-dispatch re-read failure
        # `_classify_status` reports: nothing ran, so there is no new ticket
        # state to read and the launch error itself is the reason. The status
        # logged is the pre-dispatch snapshot, which is still what's on disk.
        return _report(
            repo,
            target,
            ClassifyResult(needs_attention=True, reason=str(exc)),
            target.status,
            error=str(exc),
        )
    status, read_error = _read_status_field(target.ticket_dir)
    return _report(
        repo, target, _classify_status(status, read_error), status, exit_code=exit_code
    )


def _report(
    repo: Path,
    target: TicketInfo,
    outcome: ClassifyResult,
    status: str,
    *,
    error: str | None = None,
    exit_code: int | None = None,
) -> dict[str, object]:
    """Record a resolved dispatch and build `run_tick`'s return value.

    The log append comes before the notification so a failed notifier can never
    cost the durable record — the notification is best-effort, the log is not.
    """
    if outcome.needs_attention and outcome.reason is not None:
        _append_needs_attention(repo, target.number, outcome.reason, status)
        _notify_desktop(target.number, outcome.reason)
    return {
        "dispatched": target.number,
        "error": error,
        "exit_code": exit_code,
        "needs_attention": outcome.needs_attention,
        "reason": outcome.reason,
    }


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
    state_dir = _state_dir(repo)
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


# Positional args threaded through from cli_start's Popen call below:
# $1=python executable, $2=this script's own path, $3=repo, $4=interval
# (seconds). Keep these two definitions in lockstep — the shell has no way
# to catch a mismatch, it just loops on the wrong argument.
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


def _format_latest_attention(entries: list[dict[str, object]]) -> str:
    """The newest entry as one line, or `None` when there is nothing to report.

    Pure formatting over already-loaded entries — the count line beside it in
    `cli_status` is what says how many there were in total.
    """
    if not entries:
        return "None"
    latest = entries[-1]
    return f"{latest.get('ticket')} — {latest.get('reason')}"


def cli_status(repo: Path) -> str:
    pid_path, _, status_path = _state_paths(repo)
    pid = read_pid_file(pid_path)
    running = pid is not None and pid_is_alive(pid)
    snapshot = read_status_snapshot(status_path)
    # Read through `_load_needs_attention` so a line caught mid-write by a
    # concurrent `cli_tick` append is skipped rather than crashing `status` —
    # the one command a lead runs precisely when something has gone wrong.
    attention = _load_needs_attention(_needs_attention_path(repo))
    return "\n".join(
        [
            f"running: {running}",
            f"pid: {pid if running else None}",
            f"last_tick: {snapshot['last_tick']}",
            f"last_dispatch_outcome: {snapshot['last_dispatch_outcome']}",
            f"needs_attention: {len(attention)}",
            f"latest_attention: {_format_latest_attention(attention)}",
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
