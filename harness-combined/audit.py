"""Identity-stamped audit log (ticket 0075).

Approve/reject-type decisions — `/deliver`, `/rollback`, resolving a
`changes-requested` pause — leave no record of who made the call. `record`
appends one JSON line to `.harness/audit.log` naming who made the call;
`read` filters that log for display.

This is an accountability aid, not an access-control or tamper-evidence
mechanism (`.harness/audit.log` is a plain, gitignored local file, sibling to
`.harness/memory.db`) — identity resolution is deliberately fail-open: a
logging failure must never look like the real operation (a merge, a revert,
a lead decision) failed.
"""
from __future__ import annotations

import getpass
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _resolve_identity() -> str:
    """`git config user.name` -> `$USER` -> `getpass.getuser()` -> `"unknown"`."""
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5, shell=False,
        )
        name = result.stdout.strip()
        if result.returncode == 0 and name:
            return name
    except (OSError, subprocess.TimeoutExpired):
        pass

    user = os.environ.get("USER")
    if user:
        return user

    try:
        return getpass.getuser()
    except OSError:
        return "unknown"


def _log_path(root: Path) -> Path:
    return Path(root) / ".harness" / "audit.log"


def record(action: str, ticket: str, detail: str, *, root: Path) -> None:
    """Append one JSON line naming who performed `action` on `ticket`.

    Written as a single ``os.write()`` on an ``O_APPEND|O_CREAT`` descriptor
    (not a buffered ``.write()``, which is not guaranteed to be one syscall)
    so two concurrent callers can never interleave or corrupt either line.
    """
    log_path = _log_path(root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "who": _resolve_identity(),
        "action": action,
        "ticket": ticket,
        "detail": detail,
    }
    line = (json.dumps(entry) + "\n").encode("utf-8")
    fd = os.open(log_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def read(ticket: str | None, *, root: Path) -> list[dict]:
    """Return recorded entries, oldest first, optionally filtered by `ticket`.

    A missing file yields ``[]``. An unparseable line is skipped, never
    raised — one malformed line must not block the rest from returning.
    """
    log_path = _log_path(root)
    if not log_path.exists():
        return []
    entries: list[dict] = []
    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if ticket is None or entry.get("ticket") == ticket:
            entries.append(entry)
    return entries
