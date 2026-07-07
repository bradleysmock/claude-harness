"""Deduplicate inline PR comments before posting (ticket 0031, FR-5).

Two hash strategies, because the two finding sources differ in determinism:

* **gate** findings have deterministic messages across re-runs, so the dedup key
  is ``file:line:message``.
* **critic** findings have non-deterministic prose, so the dedup key is the stable
  structural ``file:line:severity:code``.

Rather than reconstruct a finding from a fetched comment (fragile — one format drift
silently breaks idempotency), the commenter embeds the *already-computed hash* in
every comment body as a hidden marker (``<!-- harness-finding <hash> -->``). Dedup
then just harvests those markers back out — the round-trip is exact by construction,
and it works identically for inline review comments and top-level issue comments.

Both comment surfaces are fetched (inline *and* issue comments) so a finding that
fell back to a top-level comment on a prior run is still deduplicated. A fetch
failure returns :class:`~gates.finding.DeduplicationFailed` so the orchestrator
falls back to terminal output rather than risking a double-post.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path

from gates.finding import DeduplicationFailed, Finding

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10

#: Hidden marker carrying the finding's dedup hash, embedded in every comment body.
_MARKER_RE = re.compile(r"<!-- harness-finding (?P<hash>[0-9a-f]{64}) -->")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def gate_hash(f: Finding) -> str:
    """Dedup key for a gate finding: ``file:line:message`` (messages are deterministic)."""
    return _sha(f"{f.file}:{f.line}:{f.message}")


def critic_hash(f: Finding) -> str:
    """Dedup key for a critic finding: ``file:line:severity:code`` (prose is not deterministic)."""
    return _sha(f"{f.file}:{f.line}:{f.severity}:{f.code}")


def hash_for(f: Finding, kind: str) -> str:
    """Dispatch to :func:`gate_hash` or :func:`critic_hash` by ``kind``."""
    return critic_hash(f) if kind == "critic" else gate_hash(f)


def marker_for(f: Finding, kind: str) -> str:
    """The hidden marker a comment body carries so a re-run recomputes the same key."""
    return f"<!-- harness-finding {hash_for(f, kind)} -->"


def _gh_json(api_path: str, cwd: str | None) -> list | DeduplicationFailed:
    """Fetch a paginated ``gh api`` JSON array, or return a typed failure."""
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, no command-string interpolation
            ["gh", "api", api_path, "--paginate"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=cwd,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("could not fetch existing comments (%s): %s", api_path, type(exc).__name__)
        return DeduplicationFailed(f"gh api call failed: {type(exc).__name__}")
    if proc.returncode != 0:
        logger.warning("gh api returned non-zero fetching %s", api_path)
        return DeduplicationFailed("gh api returned a non-zero exit status")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        logger.warning("could not parse comments JSON from %s: %s", api_path, exc)
        return DeduplicationFailed("existing-comments response was not valid JSON")
    if not isinstance(data, list):
        return DeduplicationFailed("existing-comments response was not a JSON array")
    return data


def fetch_existing_hashes(
    pr_number: int, repo: str, kind: str, cwd: Path | None = None
) -> set[str] | DeduplicationFailed:
    """Return every harness dedup hash already present on the PR.

    Fetches both inline review comments (``.../pulls/{pr}/comments``) and top-level
    issue comments (``.../issues/{pr}/comments``) and harvests the embedded
    ``harness-finding`` markers from all of them. ``repo`` is an ``owner/name`` spec
    (or the ``{owner}/{repo}`` template ``gh`` resolves). ``kind`` is accepted for
    API symmetry but not needed — the marker carries the pre-computed hash. On any
    subprocess/JSON failure returns :class:`DeduplicationFailed`; never raises.
    """
    cwd_str = str(cwd) if cwd is not None else None
    hashes: set[str] = set()
    for api_path in (
        f"repos/{repo}/pulls/{pr_number}/comments",
        f"repos/{repo}/issues/{pr_number}/comments",
    ):
        data = _gh_json(api_path, cwd_str)
        if isinstance(data, DeduplicationFailed):
            return data
        for comment in data:
            if isinstance(comment, dict):
                body = str(comment.get("body", "") or "")
                hashes.update(_MARKER_RE.findall(body))
    return hashes
