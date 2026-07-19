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
import re
import shutil
import subprocess
import sys
from pathlib import Path

IGNORED = {".tickets/.ticket.lock", ".tickets/.active"}
# Rename-verify steal temps (ticket 0056): transient, almost always removed
# within the same `claim()` call — a prefix rule, not an exact-match value.
IGNORED_STALE_PREFIX = ".tickets/.ticket.lock.stale-"

# The coordination branch (the design's ".harness-tickets"; git ref names cannot
# begin with a dot, so the on-disk branch drops the leading dot).
TICKETS_BRANCH = "harness-tickets"
# In-flight ticket dir: `.tickets/XXXX-<slug>/...`, but NOT `.tickets/completed/...`.
_INFLIGHT_TICKET_RE = re.compile(r"^\.tickets/\d{4}-[^/]+/")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def _has_remote(root: Path) -> bool:
    return bool(_run(root, "remote").stdout.strip())


def unpushed_ledger_commits(project_root: Path) -> list[str]:
    """Local `harness-tickets` commits not present on `origin/harness-tickets`.

    A locally-appended-but-unpushed ledger mutation reserves nothing (§1a push
    invariant) and races the next writer, so the turn must not end on one. No-op
    when git is unavailable, the branch is absent, or there is no remote at all
    (a local-only ledger is expected — nothing to publish to)."""
    if shutil.which("git") is None:
        return []
    roots = _checkout_roots(project_root)
    if not roots:
        return []
    main_root = roots[0]
    if _run(main_root, "rev-parse", "--verify", "--quiet", f"refs/heads/{TICKETS_BRANCH}").returncode != 0:
        return []  # no local coordination branch
    if not _has_remote(main_root):
        return []  # local-only repo: nothing to publish to
    origin_ref = f"refs/remotes/origin/{TICKETS_BRANCH}"
    if _run(main_root, "rev-parse", "--verify", "--quiet", origin_ref).returncode != 0:
        # a local ledger branch with no origin counterpart is entirely unpushed
        rev = _run(main_root, "rev-list", TICKETS_BRANCH)
    else:
        rev = _run(main_root, "rev-list", f"{origin_ref}..{TICKETS_BRANCH}")
    return [line for line in rev.stdout.splitlines() if line.strip()]


def is_tickets_branch_merge(source_ref: str) -> bool:
    """True when `source_ref` names the coordination branch — such a merge into
    `main` must be refused (the orphan branch is never merged)."""
    name = source_ref.strip()
    if name.startswith("refs/heads/"):
        name = name[len("refs/heads/"):]
    if "/" in name:
        name = name.rsplit("/", 1)[1]
    return name == TICKETS_BRANCH


def staged_inflight_ticket_dirs(project_root: Path) -> list[str]:
    """Staged (index) paths under an in-flight `.tickets/XXXX-<slug>/` dir on the
    current branch — `completed/` is allowed, an in-flight dir on a `main` commit
    is not (Option 1: only delivered ticket docs reach `main`)."""
    if shutil.which("git") is None:
        return []
    proc = _run(project_root, "diff", "--cached", "--name-only", "--", ".tickets/")
    if proc.returncode != 0:
        return []
    return [
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip() and _INFLIGHT_TICKET_RE.match(line.strip())
    ]


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
            if path in IGNORED or path.startswith(IGNORED_STALE_PREFIX):
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
    unpushed = unpushed_ledger_commits(project_root)
    if not dirty and not unpushed:
        return 0
    if dirty:
        sys.stderr.write(
            "ticket_commit_guard blocked completion — uncommitted ticket metadata:\n\n"
            + "\n".join(f"  {p}" for p in dirty)
            + "\n\nCommit each ticket's metadata before ending the turn "
            "(use `ticket set-status <id> <status>` or a scoped `git add .tickets/<id>/`).\n"
        )
    if unpushed:
        sys.stderr.write(
            f"\nticket_commit_guard blocked completion — {len(unpushed)} unpushed "
            f"{TICKETS_BRANCH} ledger commit(s):\n\n"
            + "\n".join(f"  {sha}" for sha in unpushed)
            + "\n\nA local-only ledger mutation reserves nothing and races the next "
            "writer. Push harness-tickets to origin before ending the turn.\n"
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
