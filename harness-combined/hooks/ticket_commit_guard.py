#!/usr/bin/env python3
# harness-combined/hooks/ticket_commit_guard.py
"""Stop hook: block turn-end if ticket metadata is left uncommitted.

Mirrors stop_full_gate.py's contract: exit 2 + stderr blocks completion. The
orphaned-update bug exists because status edits and their commits were two
separate hand-run steps; this guard makes leaving them uncommitted impossible.

With branch-at-claim, ticket metadata lives in two kinds of checkout: the main
root (`main`'s `.tickets/`) and each active worktree under `.worktrees/<slug>/`.
The guard discovers every checkout via `git worktree list` — anchored on the main
root resolved with `git rev-parse --git-common-dir` so it works whether the turn's
cwd is the main root or inside a worktree — and scans `.tickets/` in each. A ticket
dir that is simply absent on `main` (a branch-only ticket) is never flagged: each
checkout's own `git status` only reports files present in that checkout.

No-op when git is unavailable or no checkout has a `.tickets/` directory.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

IGNORED = {".tickets/.ticket.lock", ".tickets/.active"}


def _checkout_roots(start: Path) -> list[Path]:
    """Return every checkout root for this repo: the main root first, then each
    worktree. Anchored on the main root (via `--git-common-dir`'s parent) so the
    set is identical no matter which checkout `start` points into."""
    common = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, check=False,
    )
    if common.returncode != 0:
        return []
    git_common = Path(common.stdout.strip())
    if not git_common.is_absolute():
        git_common = Path(start) / git_common
    main_root = git_common.resolve().parent

    listing = subprocess.run(
        ["git", "-C", str(main_root), "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=False,
    )
    # Resolve every path to one canonical form so identity comparisons and
    # `relative_to` below are sound — `--git-common-dir` returns a resolved path
    # (e.g. /private/var/... on macOS) while the porcelain listing may report the
    # unresolved form (/var/...), which would otherwise alias the main root.
    roots: list[Path] = []
    for line in listing.stdout.splitlines():
        if line.startswith("worktree "):
            root = Path(line[len("worktree "):].strip()).resolve()
            if root not in roots:
                roots.append(root)
    if main_root not in roots:
        roots.insert(0, main_root)
    return roots


def dirty_ticket_files(project_root: Path) -> list[str]:
    if shutil.which("git") is None:
        return []
    roots = _checkout_roots(project_root)
    if not roots:
        return []
    main_root = roots[0]
    dirty: list[str] = []
    for root in roots:
        if not (root / ".tickets").is_dir():
            continue
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--", ".tickets/"],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            path = line[3:].strip()  # strip the 2-char status code + space
            if " -> " in path:  # rename: keep the destination path
                path = path.rsplit(" -> ", 1)[1]
            if path in IGNORED:
                continue
            # Prefix worktree findings so the lead can tell which checkout they
            # are in; main-root findings keep their bare `.tickets/...` path.
            if root == main_root:
                dirty.append(path)
            else:
                try:
                    rel = root.resolve().relative_to(main_root)
                except ValueError:
                    rel = Path(root.name)
                dirty.append(f"{rel}/{path}")
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
