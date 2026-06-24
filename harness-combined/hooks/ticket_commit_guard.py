#!/usr/bin/env python3
# harness-combined/hooks/ticket_commit_guard.py
"""Stop hook: block turn-end if ticket metadata is left uncommitted.

Mirrors stop_full_gate.py's contract: exit 2 + stderr blocks completion. The
orphaned-update bug exists because status edits and their commits were two
separate hand-run steps; this guard makes leaving them uncommitted impossible.

No-op when there is no .tickets/ directory or git is unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

IGNORED = {".tickets/.ticket.lock", ".tickets/.active"}


def dirty_ticket_files(project_root: Path) -> list[str]:
    if not (project_root / ".tickets").is_dir() or shutil.which("git") is None:
        return []
    proc = subprocess.run(
        ["git", "-C", str(project_root), "status", "--porcelain", "--", ".tickets/"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return []
    dirty: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()  # strip the 2-char status code + space
        if path in IGNORED:
            continue
        dirty.append(path)
    return dirty


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    project_root = Path(payload.get("cwd") or Path.cwd())
    dirty = dirty_ticket_files(project_root)
    if not dirty:
        return 0
    sys.stderr.write(
        "ticket_commit_guard blocked completion — uncommitted ticket metadata:\n\n"
        + "\n".join(f"  {p}" for p in dirty)
        + "\n\nCommit each ticket's metadata before ending the turn "
        "(use `ticket set-status <id> <status>` or a scoped `git add .tickets/<id>/`).\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
