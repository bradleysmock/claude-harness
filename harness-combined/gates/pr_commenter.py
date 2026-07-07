"""Orchestrate inline PR comment posting (ticket 0031).

Wires :mod:`gates.pr_detector` and :mod:`gates.comment_deduplicator` into a single
entry point, :func:`post_findings`. Every failure mode falls back to terminal output
(via the module logger — the project uses a logger, not stdout) with the specific
message from the ticket's Failure Mode table, and returns
:class:`~gates.finding.PostResult` so callers assert on counts, not printed text.

Routing (FR-3): a finding whose ``file:line`` is actually in the PR diff becomes an
inline review comment; a finding that is off-diff or carries no location becomes a
top-level issue comment. This keeps GitHub from rejecting the whole review batch
with a 422 when one line is outside the diff. Both surfaces carry a hidden dedup
marker so re-runs post nothing new (FR-5).

Security posture: ``head_oid`` from ``gh`` is validated against a strict SHA regex
before it enters the API payload; inline findings post in exactly one ``gh api``
review submission (argument list, no shell); a token is never logged.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from gates.comment_deduplicator import fetch_existing_hashes, hash_for, marker_for
from gates.finding import (
    DeduplicationFailed,
    Finding,
    GhUnavailable,
    NoPRFound,
    NotAuthenticated,
    PostResult,
    PR,
    validate_finding,
)

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10

#: Fail-closed against GitHub's 65,535-char body limit.
_BODY_LIMIT = 60_000

#: SHA-1 (40) or SHA-256 (64) lowercase-hex commit id.
_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")

#: ``gh`` fills these from the current remote, so no owner/name lookup is needed.
_REPO_TEMPLATE = "{owner}/{repo}"

#: Severities whose comment body is prefixed as a suggestion (FR-4).
_SUGGESTION_SEVERITIES = frozenset({"MINOR", "OBS"})


def format_summary(result: PostResult) -> str:
    """Render the operator-facing summary line (FR-10)."""
    return f"Posted {result.posted} inline comments ({result.skipped} skipped as duplicates)."


def _dump_to_terminal(findings: list[Finding]) -> None:
    """Emit findings to the terminal (via logger, warning level — the fallback output)."""
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.file else "(no location)"
        logger.warning("[%s] %s — %s", f.severity, loc, f.message)


def _decorate(f: Finding, kind: str) -> str:
    """The message body, adding the ``[suggestion]`` prefix for MINOR/OBS (FR-4)."""
    if f.severity.upper() in _SUGGESTION_SEVERITIES:
        return f"[suggestion] {f.message}"
    return f.message


def _inline_body(f: Finding, kind: str) -> str:
    """An inline review comment body: decorated message plus the hidden dedup marker."""
    return f"{_decorate(f, kind)}\n\n{marker_for(f, kind)}"


def _toplevel_line(f: Finding, kind: str) -> str:
    """One rendered line for a top-level issue comment, carrying its dedup marker."""
    loc = f"{f.file}:{f.line}" if f.file else "(no file:line)"
    return f"- **{f.severity}** {loc} — {_decorate(f, kind)} {marker_for(f, kind)}"


def _is_inline(f: Finding, diff_map: dict[str, set[int]] | None) -> bool:
    """True iff the finding should post inline (has a location that is in the diff).

    When ``diff_map`` is ``None`` (the diff could not be fetched), fall back to
    best-effort: any finding with a ``file:line`` is treated as inline, and a 422
    from the submission demotes it to top-level.
    """
    if not f.file or f.line is None:
        return False
    if diff_map is None:
        return True
    return f.line in diff_map.get(f.file, set())


def _submit_review(payload: dict, cwd: str | None) -> str:
    """POST one review with all inline comments. Returns ``ok`` / ``off_diff`` / ``error``."""
    api_path = f"repos/{_REPO_TEMPLATE}/pulls/{payload['_pr_number']}/reviews"
    body = {k: v for k, v in payload.items() if not k.startswith("_")}
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell; JSON travels via stdin
            ["gh", "api", "--method", "POST", api_path, "--input", "-"],
            input=json.dumps(body),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=cwd,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("gh api review submission failed: %s", type(exc).__name__)
        return "error"
    if proc.returncode == 0:
        return "ok"
    stderr = (proc.stderr or "").lower()
    if "422" in stderr or "diff" in stderr:
        logger.warning("review rejected (line not in diff); demoting to top-level comment")
        return "off_diff"
    logger.warning("gh api review submission returned a non-zero exit status")
    return "error"


def _submit_issue_comment(body: str, pr_number: int, cwd: str | None) -> bool:
    """POST a single top-level issue comment. Returns success."""
    api_path = f"repos/{_REPO_TEMPLATE}/issues/{pr_number}/comments"
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell; JSON travels via stdin
            ["gh", "api", "--method", "POST", api_path, "--input", "-"],
            input=json.dumps({"body": body}),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=cwd,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("gh api issue-comment submission failed: %s", type(exc).__name__)
        return False
    if proc.returncode != 0:
        logger.warning("gh api issue-comment submission returned a non-zero exit status")
        return False
    return True


def _render_toplevel_body(findings: list[Finding], kind: str) -> str:
    """Assemble the top-level issue comment body, collapsing to a summary if oversized.

    The full render lists each finding with its dedup marker. If that exceeds the
    body limit (NFR-1), fall back to a compact summary that still carries every
    marker (so dedup holds) and points at ``gate-findings.md``.
    """
    full = "\n".join(_toplevel_line(f, kind) for f in findings)
    if len(full) <= _BODY_LIMIT:
        return full
    markers = " ".join(marker_for(f, kind) for f in findings)
    locs = ", ".join(f"{f.file or '(no file)'}:{f.line}" for f in findings)
    return (
        "Harness findings exceeded the inline comment size limit; see "
        f"`gate-findings.md`. Findings: {locs}\n\n{markers}"
    )


def post_findings(
    findings: list[Finding],
    worktree_root: Path,
    should_post: bool,
    dry_run: bool = False,
    kind: str = "gate",
    cwd: Path | None = None,
) -> PostResult:
    """Post ``findings`` as PR comments (inline where in-diff, top-level otherwise).

    ``should_post=False`` is the opt-out seam (FR-8): findings go to the terminal
    and no ``gh`` subprocess runs. Otherwise the open PR is detected, its
    ``head_oid`` SHA-validated, existing comments fetched for dedup, and new
    findings routed by diff membership. Any failure mode returns a
    ``PostResult`` after a specific terminal notice. ``dry_run`` computes the same
    result without submitting.
    """
    root = Path(worktree_root).resolve()
    cwd_str = str(cwd) if cwd is not None else None

    if not should_post:
        _dump_to_terminal(findings)
        return PostResult(posted=0, skipped=0)

    from gates.pr_detector import detect_pr, fetch_diff_lines  # local: keep model import cheap

    pr = detect_pr(cwd=cwd)
    match pr:
        case GhUnavailable():
            logger.warning("gh not installed — outputting to terminal only")
            _dump_to_terminal(findings)
            return PostResult(0, 0)
        case NotAuthenticated():
            logger.warning("gh not authenticated — outputting to terminal only")
            _dump_to_terminal(findings)
            return PostResult(0, 0)
        case NoPRFound():
            logger.warning("No open PR for this branch — outputting to terminal only")
            _dump_to_terminal(findings)
            return PostResult(0, 0)
        case PR():
            resolved_pr = pr

    if not _SHA_RE.match(resolved_pr.head_oid):
        logger.warning("Invalid commit SHA from gh — aborting post; outputting to terminal only")
        _dump_to_terminal(findings)
        return PostResult(0, 0)

    existing = fetch_existing_hashes(resolved_pr.number, _REPO_TEMPLATE, kind, cwd=cwd)
    if isinstance(existing, DeduplicationFailed):
        logger.warning(
            "Could not fetch existing comments — aborting to avoid duplicates; "
            "outputting to terminal only"
        )
        _dump_to_terminal(findings)
        return PostResult(0, 0)

    # Defensive containment re-check at the trust boundary: the parsers validate,
    # but the orchestrator must never post a finding whose file escapes the worktree.
    safe_findings = [f for f in findings if validate_finding(f, root)]
    if len(safe_findings) != len(findings):
        logger.warning("dropped %d finding(s) failing containment at post time", len(findings) - len(safe_findings))

    new_findings: list[Finding] = []
    skipped = 0
    for f in safe_findings:
        if hash_for(f, kind) in existing:
            skipped += 1
        else:
            new_findings.append(f)
    if not new_findings:
        return PostResult(posted=0, skipped=skipped)

    diff_map = fetch_diff_lines(resolved_pr.number, _REPO_TEMPLATE, cwd=cwd)
    inline: list[Finding] = []
    top_level: list[Finding] = []
    for f in new_findings:
        (inline if _is_inline(f, diff_map) else top_level).append(f)

    # An oversized inline batch collapses to the top-level surface (NFR-1).
    inline_bodies = [_inline_body(f, kind) for f in inline]
    if sum(len(b) for b in inline_bodies) > _BODY_LIMIT:
        top_level = inline + top_level
        inline, inline_bodies = [], []

    posted = 0

    if inline:
        payload = {
            "_pr_number": resolved_pr.number,
            "commit_id": resolved_pr.head_oid,
            "event": "COMMENT",
            "body": "",
            "comments": [
                {"path": f.file, "line": f.line, "side": "RIGHT", "body": body}
                for f, body in zip(inline, inline_bodies)
            ],
        }
        if dry_run:
            posted += len(inline)
        else:
            result = _submit_review(payload, cwd_str)
            if result == "ok":
                posted += len(inline)
            elif result == "off_diff":
                top_level = inline + top_level  # diff map was unavailable; demote and retry
            else:
                _dump_to_terminal(findings)
                return PostResult(posted, skipped)

    if top_level:
        body = _render_toplevel_body(top_level, kind)
        if dry_run:
            posted += len(top_level)
        elif _submit_issue_comment(body, resolved_pr.number, cwd_str):
            posted += len(top_level)
        else:
            _dump_to_terminal(findings)
            return PostResult(posted, skipped)

    return PostResult(posted=posted, skipped=skipped)
