"""Shared data model for inline PR comment posting (ticket 0031).

Kept separate from :mod:`gates.sast_models` (which has its own ``Finding`` carrying
a tiered ``Severity`` enum and ``rule_id``): this ``Finding`` models a *reviewable*
gate/critic finding — a ``file:line`` anchor plus a free-text ``severity`` string
(``BLOCKER``/``MAJOR``/``MINOR``/``OBS`` for critics; ``MAJOR`` default for gate
findings). The typed result types (:class:`PR`, :class:`GhUnavailable`,
:class:`NotAuthenticated`, :class:`NoPRFound`, :class:`DeduplicationFailed`) are
named for *what happened*, not what happens next, so the orchestrator dispatches on
type rather than matching on a ``reason`` string (avoids Hyrum's-Law coupling).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Finding:
    """A single reviewable finding with a ``file:line`` anchor.

    ``file`` is relative to the scanned worktree (or ``""`` for a finding that has
    no location and must fall back to a top-level PR comment); ``line`` is
    1-indexed or ``None`` when the finding is not tied to a specific line;
    ``severity`` is the free-text tier; ``code`` is the rule/check id (may be
    ``""``); ``message`` is the human-readable body.
    """

    file: str
    line: int | None
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class PR:
    """An open GitHub PR for the current branch."""

    number: int
    head_ref: str
    head_oid: str


@dataclass(frozen=True)
class GhUnavailable:
    """The ``gh`` binary is not installed / not on PATH."""

    reason: str


@dataclass(frozen=True)
class NotAuthenticated:
    """``gh auth status`` reported the user is not authenticated."""

    reason: str


@dataclass(frozen=True)
class NoPRFound:
    """No open PR exists for the current branch (zero-field sentinel)."""


@dataclass(frozen=True)
class DeduplicationFailed:
    """Fetching existing PR comments failed; abort posting to avoid duplicates."""

    reason: str


@dataclass(frozen=True)
class PostResult:
    """Outcome of a posting run: how many comments were posted vs. skipped."""

    posted: int
    skipped: int


def validate_finding(f: Finding, worktree_root: Path) -> bool:
    """Return ``True`` iff ``f`` is safe to post.

    Preconditions: ``worktree_root`` is an already-canonicalized absolute
    :class:`~pathlib.Path` (caller responsibility — the orchestrator resolves it
    once). A finding validates iff its ``file`` resolves *inside* ``worktree_root``
    (containment; a path escaping the root via ``..`` or an absolute path is
    rejected), its ``line`` is either ``None`` or a positive integer, and its
    ``severity`` is a non-empty string. Never raises on malformed input — a bad
    path or value returns ``False``.
    """
    if not isinstance(f.severity, str) or not f.severity.strip():
        return False
    if f.line is not None:
        # bool is an int subclass; a line number that is a bool is malformed.
        if isinstance(f.line, bool) or not isinstance(f.line, int) or f.line <= 0:
            return False
    try:
        candidate = Path(f.file)
        if not candidate.is_absolute():
            candidate = worktree_root / candidate
        return candidate.resolve().is_relative_to(worktree_root)
    except (OSError, ValueError):
        return False
