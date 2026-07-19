"""Detect the open GitHub PR for the current branch via ``gh`` (ticket 0031).

Returns a typed result — :class:`~gates.finding.PR` on success, or one of
:class:`~gates.finding.GhUnavailable` / :class:`~gates.finding.NotAuthenticated` /
:class:`~gates.finding.NoPRFound`. Every ``gh`` invocation passes an argument list
(never an interpolated command string, never via the shell) with a bounded timeout;
auth output is never logged, to keep tokens out of any artifact.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from gates.finding import PR, GhUnavailable, NoPRFound, NotAuthenticated

logger = logging.getLogger(__name__)

#: Bounded so a hung ``gh`` never stalls the gate run (NFR-1).
_TIMEOUT_SECONDS = 10

#: New-file starting line of a unified-diff hunk header: ``@@ -a,b +c,d @@``.
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,\d+)? @@")


def _run(args: list[str], cwd: str | None) -> subprocess.CompletedProcess[str]:
    """Run ``args`` capturing text output with a bounded timeout (argument list only)."""
    return subprocess.run(  # noqa: S603 — fixed argument list, no shell, no interpolation
        args, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, cwd=cwd
    )


def detect_pr(cwd: Path | None = None) -> PR | GhUnavailable | NotAuthenticated | NoPRFound:
    """Probe ``gh`` for an open PR on the current branch.

    Probe order: binary presence (``FileNotFoundError`` → ``GhUnavailable``) and
    auth (``gh auth status`` non-zero → ``NotAuthenticated``), then ``gh pr view``
    (non-zero → ``NoPRFound``). A malformed JSON payload or a timeout on ``pr
    view`` degrades to ``NoPRFound``; a timeout probing auth degrades to
    ``GhUnavailable``. Never raises.
    """
    cwd_str = str(cwd) if cwd is not None else None

    try:
        auth = _run(["gh", "auth", "status"], cwd_str)
    except FileNotFoundError:
        return GhUnavailable("gh binary not found on PATH")
    except subprocess.TimeoutExpired:
        return GhUnavailable("gh auth status timed out")
    if auth.returncode != 0:
        return NotAuthenticated("gh reports the user is not authenticated")

    try:
        view = _run(["gh", "pr", "view", "--json", "number,headRefName,headRefOid"], cwd_str)
    except FileNotFoundError:
        return GhUnavailable("gh binary not found on PATH")
    except subprocess.TimeoutExpired:
        logger.warning("gh pr view timed out; treating as no open PR")
        return NoPRFound()
    if view.returncode != 0:
        return NoPRFound()

    try:
        data = json.loads(view.stdout)
        return PR(
            number=int(data["number"]),
            head_ref=str(data["headRefName"]),
            head_oid=str(data["headRefOid"]),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning("could not parse gh pr view JSON: %s", exc)
        return NoPRFound()


def _commentable_lines(patch: str) -> set[int]:
    """New-file line numbers that GitHub will accept an inline comment on.

    Added (``+``) and context (`` ``) lines within a hunk are commentable; removed
    (``-``) lines exist only in the old file and are skipped.
    """
    lines: set[int] = set()
    new_ln = 0
    for row in patch.splitlines():
        hunk = _HUNK_RE.match(row)
        if hunk is not None:
            new_ln = int(hunk.group("start"))
            continue
        if new_ln == 0:  # text before the first hunk header
            continue
        if row.startswith("\\"):
            continue  # "\ No newline at end of file" — not a real line; must not advance
        if row.startswith("+"):
            lines.add(new_ln)
            new_ln += 1
        elif row.startswith("-"):
            continue
        else:  # context line
            lines.add(new_ln)
            new_ln += 1
    return lines


def fetch_diff_lines(pr_number: int, repo: str, cwd: Path | None = None) -> dict[str, set[int]] | None:
    """Map each changed file to the new-file line numbers commentable in the PR diff.

    Fetches ``.../pulls/{pr}/files`` and parses each file's unified-diff ``patch``.
    Used to route findings whose line is *not* in the diff to a top-level comment
    (FR-3), avoiding a 422 that would reject the whole review batch. Returns
    ``None`` on any failure so the caller can fall back to best-effort behaviour;
    never raises.
    """
    cwd_str = str(cwd) if cwd is not None else None
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, no command-string interpolation
            ["gh", "api", f"repos/{repo}/pulls/{pr_number}/files", "--paginate"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=cwd_str,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("could not fetch PR diff files: %s", type(exc).__name__)
        return None
    if proc.returncode != 0:
        logger.warning("gh api pulls/files returned a non-zero exit status")
        return None
    try:
        files = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        logger.warning("could not parse PR files JSON: %s", exc)
        return None
    if not isinstance(files, list):
        return None

    diff_map: dict[str, set[int]] = {}
    for entry in files:
        if not isinstance(entry, dict):
            continue
        filename = entry.get("filename")
        patch = entry.get("patch")
        if isinstance(filename, str) and isinstance(patch, str):
            diff_map[filename] = _commentable_lines(patch)
    return diff_map
