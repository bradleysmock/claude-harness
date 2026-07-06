"""Shared filesystem helpers for the SAST adapters (ticket 0025).

Containment and path-relativization are security-critical (a config path that
escapes the project root, or a tool that reports a path outside the scanned
worktree). A single tested implementation is safer than duplicating the logic in
each adapter, and it keeps :mod:`gates.sast_models` free of filesystem I/O.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path


def tool_available(name: str) -> bool:
    """True if ``name`` is runnable as a binary on PATH or importable as a module.

    Bandit ships as a Python module (``python -m bandit``) and often has no
    standalone launcher; Semgrep is normally a binary. Checking both covers the
    graceful-skip contract (FR-8) in either install shape.
    """
    if shutil.which(name) is not None:
        return True
    return importlib.util.find_spec(name) is not None


def resolve_contained(config_path: Path, root: Path) -> Path | None:
    """Return ``config_path`` resolved iff it exists and stays inside ``root``.

    Both sides are fully resolved (following symlinks) before the containment
    test, so a symlinked config that escapes ``root`` is rejected. Returns
    ``None`` when the file is absent or escapes — the caller falls back to the
    tool's default ruleset. Never raises on a bad path.
    """
    try:
        if not config_path.exists():
            return None
        resolved = config_path.resolve()
        if resolved.is_relative_to(root.resolve()):
            return resolved
    except OSError:
        return None
    return None


def relativize(raw_path: str, worktree: Path) -> str | None:
    """Normalise a tool-reported path to be relative to ``worktree``.

    Returns the POSIX-style relative path, or ``None`` when the path resolves
    outside the worktree (the caller discards the finding and warns). Never
    raises.
    """
    try:
        resolved = Path(raw_path)
        if not resolved.is_absolute():
            resolved = (worktree / raw_path)
        rel = resolved.resolve().relative_to(worktree.resolve())
    except (OSError, ValueError):
        return None
    return rel.as_posix()
