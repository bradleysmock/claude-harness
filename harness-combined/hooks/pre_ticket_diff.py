#!/usr/bin/env python3
"""PreToolUse hook: show a unified diff of a pending ticket-artifact write.

Before a Write/Edit/MultiEdit to a ``.tickets/**/*.md`` file that already exists
with non-empty content, this hook prints a standard unified diff of the pending
change to stderr so the harness operator can review what ``/refine`` (or any
command that overwrites a ticket artifact) is about to change. It then always
exits 0 — it is a display hook and must never block a write.

All skip and failure paths exit 0 silently: file absent, content unchanged,
target outside ``.tickets/``, unreadable file, an Edit ``old_string`` that does
not match, or ``HARNESS_NO_DIFF=1`` set in the environment. The diff goes to
stderr (stdout may carry protocol semantics for PreToolUse) and is computed
in-process with :mod:`difflib` — no subprocess.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# _common is a sibling module; the line above puts this hook's directory on
# sys.path so the import resolves both when run as a script and when a test
# loads this file via importlib.
from _common import extract_file_path  # noqa: E402 — sibling import, path set above


def _tickets_root() -> Path:
    """The ``.tickets/`` directory under the current working directory.

    Hooks run with cwd at the project root, where ``.tickets/`` lives. Resolved
    non-strictly so a missing directory yields a path that simply contains
    nothing (every containment check then returns False).
    """
    return (Path.cwd() / ".tickets").resolve()


def is_ticket_artifact(file_path: str) -> bool:
    """True when ``file_path`` resolves to a ``*.md`` file inside ``.tickets/``.

    Uses ``Path.resolve().is_relative_to()`` so ``../`` traversal and absolute
    paths that merely string-contain ``.tickets`` are rejected (FR-1).
    """
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError):
        return False
    if resolved.suffix.lower() != ".md":
        return False
    return resolved.is_relative_to(_tickets_root())


def should_show_diff(file_path: str) -> bool:
    """True only when a diff is warranted: a contained ticket ``.md`` that
    already exists with non-empty content (FR-4, FR-5, NFR-2)."""
    if not is_ticket_artifact(file_path):
        return False
    path = Path(file_path)
    try:
        if not path.is_file():
            return False
        return bool(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        # UnicodeDecodeError is a ValueError, not an OSError; a non-UTF-8 file
        # must still degrade to "no diff", never crash the hook (NFR-2).
        return False


def apply_patches(current_text: str, edits: list[dict]) -> str | None:
    """Apply ``{'old_string','new_string'}`` edits sequentially, replacing the
    first occurrence of each ``old_string``.

    Returns the resulting text, or ``None`` if any ``old_string`` is empty or
    not found in the working text — the signal to skip the diff (the subsequent
    real write would fail the same way).
    """
    text = current_text
    for edit in edits:
        old = edit.get("old_string", "")
        new = edit.get("new_string", "")
        if not old:
            return None
        index = text.find(old)
        if index == -1:
            return None
        text = text[:index] + new + text[index + len(old):]
    return text


def reconstruct_proposed_content(
    tool_name: str, tool_input: dict, current_text: str
) -> str | None:
    """Reconstruct the full proposed file content for the pending write.

    ``Write`` uses ``content`` directly; ``Edit`` / ``MultiEdit`` apply their
    patches onto ``current_text``. Returns ``None`` when reconstruction is not
    possible (unknown tool, or an unmatched ``old_string``).
    """
    if tool_name == "Write":
        content = tool_input.get("content", "")
        return content if isinstance(content, str) else None
    if tool_name == "Edit":
        return apply_patches(
            current_text,
            [{
                "old_string": tool_input.get("old_string", ""),
                "new_string": tool_input.get("new_string", ""),
            }],
        )
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", []) or []
        return apply_patches(current_text, edits)
    return None


def compute_diff(old: str, new: str, file_path: str) -> str:
    """Unified diff of ``old`` vs ``new`` (``''`` when identical, FR-5).

    Standard unified format with ``--- a/name`` / ``+++ b/name`` headers and
    ``@@`` hunks (FR-6).
    """
    if old == new:
        return ""
    name = Path(file_path).name
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{name}",
        tofile=f"b/{name}",
    )
    return "".join(lines)


def main() -> int:
    if os.environ.get("HARNESS_NO_DIFF") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    file_path = extract_file_path(tool_name, tool_input)
    if not file_path or not should_show_diff(file_path):
        return 0

    try:
        current = Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # See should_show_diff: a non-UTF-8 or unreadable file is a silent
        # exit-0 path, not a traceback (NFR-2).
        return 0

    proposed = reconstruct_proposed_content(tool_name, tool_input, current)
    if proposed is None:
        return 0

    diff = compute_diff(current, proposed, file_path)
    if diff:
        sys.stderr.write(diff)
        if not diff.endswith("\n"):
            sys.stderr.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
