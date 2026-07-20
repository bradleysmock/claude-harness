"""Diff-scoping and brief formatting for incremental critic rounds (ticket 0067).

The repair loop's round-1 critic (``build-ticket.md`` Step 7) always reads the full
worktree. Round 2+ re-spawns (Step 7a) instead hand the critic an *incremental*
brief scoped to the round's own diff plus the prior round's still-open BLOCKER/MAJOR
findings — this module supplies the two pure functions that make that brief:
:func:`touched_files_from_diff` (which files did the round actually touch) and
:func:`format_incremental_brief` (the brief text itself). Both are pure text-in/
text-out — no file I/O, no git subprocess calls; the caller (``build-ticket.md``
Step 7a's prep sub-step) supplies ``diff_text`` (captured via ``git diff``) and
``worktree_root`` (an already-resolved absolute path).
"""

from __future__ import annotations

import re
from pathlib import Path

from gates.finding import Finding

#: A rename pair: "rename from <path>" followed later by "rename to <path>".
_RENAME_FROM_RE = re.compile(r"^rename from (?P<path>.+)$")
_RENAME_TO_RE = re.compile(r"^rename to (?P<path>.+)$")

#: "Binary files a/<path> and b/<path> differ" — no hunk body to parse.
_BINARY_RE = re.compile(r"^Binary files (?P<old>\S+) and (?P<new>\S+) differ$")


def _strip_ab(path: str) -> str:
    """Drop a unified-diff ``a/``/``b/`` prefix and any trailing tab timestamp."""
    path = path.strip().split("\t", 1)[0]
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _contained(path: str, worktree_root: Path) -> str | None:
    """Return ``path`` if it resolves inside ``worktree_root``, else ``None``.

    Mirrors ``gates/finding.py``'s ``validate_finding`` containment convention:
    resolve relative to the root, then require ``is_relative_to``. Never raises —
    an unparseable or escaping path is dropped, not surfaced as an error.
    """
    if not path or path in ("", "/dev/null"):
        return None
    try:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = worktree_root / candidate
        if candidate.resolve().is_relative_to(worktree_root):
            return path
    except (OSError, ValueError):
        return None
    return None


def _add_if_contained(path: str, worktree_root: Path, touched: set[str]) -> None:
    """Add ``path`` to ``touched`` if it resolves inside ``worktree_root``; no-op otherwise."""
    contained = _contained(path, worktree_root)
    if contained:
        touched.add(contained)


def touched_files_from_diff(diff_text: str, worktree_root: Path) -> list[str]:
    """Return the sorted, de-duplicated, contained paths a unified diff touches.

    Add/modify hunks contribute only the new (``+++ b/…``) side; delete hunks
    contribute only the old (``--- a/…``) side; a rename contributes both the old
    and new path; a "Binary files … differ" line contributes both named paths
    without attempting hunk parsing. Every candidate path is checked for
    containment against ``worktree_root`` (an already-resolved absolute
    ``Path`` — caller responsibility, matching ``validate_finding``'s
    precondition); an escaping or unparseable path is silently dropped. Malformed
    or empty ``diff_text`` returns ``[]``. Never raises.
    """
    if not diff_text or not isinstance(diff_text, str):
        return []

    touched: set[str] = set()
    old_path = ""

    for line in diff_text.splitlines():
        binary = _BINARY_RE.match(line)
        if binary is not None:
            for path in (_strip_ab(binary.group("old")), _strip_ab(binary.group("new"))):
                _add_if_contained(path, worktree_root, touched)
            continue

        rename_from = _RENAME_FROM_RE.match(line)
        if rename_from is not None:
            _add_if_contained(rename_from.group("path").strip(), worktree_root, touched)
            continue

        rename_to = _RENAME_TO_RE.match(line)
        if rename_to is not None:
            _add_if_contained(rename_to.group("path").strip(), worktree_root, touched)
            continue

        if line.startswith("--- "):
            old_path = _strip_ab(line[4:])
            continue

        if line.startswith("+++ "):
            new_path = _strip_ab(line[4:])
            if new_path in ("", "/dev/null"):
                # Deletion: only the old side exists.
                _add_if_contained(old_path, worktree_root, touched)
            else:
                _add_if_contained(new_path, worktree_root, touched)
            old_path = ""
            continue

    return sorted(touched)


def _finding_header(f: Finding) -> str:
    """Render a Finding's header line in the same grammar the critic emits."""
    location = f"`{f.file}:{f.line}`" if f.file else ""
    code = f" · {f.code}" if f.code else ""
    parts = [f"**{f.severity}**{code}"]
    if location:
        parts.append(location)
    return " · ".join(parts)


def format_incremental_brief(prior_findings: list[Finding], diff_text: str) -> str:
    """Render the incremental round's brief: prior findings, then the round's diff.

    Deterministic and pure — no filtering, sorting, or de-duplication of
    ``prior_findings`` (callers pass them in ``critic-findings.md`` document
    order). Never raises on an empty ``prior_findings`` list or empty
    ``diff_text``; both render an explicit placeholder line instead of an empty
    section.
    """
    lines: list[str] = ["Mode: incremental", ""]

    lines.append("## Prior BLOCKER/MAJOR findings")
    lines.append("")
    if not prior_findings:
        lines.append("No prior BLOCKER/MAJOR findings carried forward.")
    else:
        for f in prior_findings:
            lines.append(_finding_header(f))
            if f.message:
                lines.append(f.message)
            lines.append("")
    lines.append("")

    lines.append("## Round diff")
    lines.append("")
    if not diff_text or not diff_text.strip():
        lines.append("No diff captured for this round.")
    else:
        lines.append("```diff")
        lines.append(diff_text)
        lines.append("```")

    return "\n".join(lines)
