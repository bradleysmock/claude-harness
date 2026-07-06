#!/usr/bin/env python3
"""Shared helpers for the PreToolUse hooks.

Deliberately minimal: it exports only :func:`extract_file_path` so that
``pre_write_guard.py`` and ``pre_ticket_diff.py`` extract the target path the
same way without either hook importing the other. No diff, patch, or
violation-scanning logic lives here — those needs are irreconcilable between the
two hooks (the guard scans the incoming fragment; the diff hook reconstructs the
full file), so only the path extraction is shared.
"""

from __future__ import annotations

#: Tools whose PreToolUse payload carries a ``file_path`` in ``tool_input``.
_PATH_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})


def extract_file_path(tool_name: str, tool_input: dict) -> str | None:
    """Return the target file path for a Write/Edit/MultiEdit payload.

    Returns ``tool_input['file_path']`` for those three tools and ``None`` for
    any other tool or when ``file_path`` is absent — never raises ``KeyError``.
    """
    if tool_name not in _PATH_TOOLS:
        return None
    path = tool_input.get("file_path")
    return path if isinstance(path, str) and path else None
