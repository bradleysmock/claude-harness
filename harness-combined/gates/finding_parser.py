"""Parse ``gate-findings.md`` into validated :class:`~gates.finding.Finding` objects.

The gate writes findings as ``- `<file>:<line>` [`<code>`]: <message>`` (the
``[`<code>`]`` segment is optional). Gate findings carry no explicit severity tier
in this grammar, so they default to ``MAJOR``. Findings whose line is not an integer
or whose file escapes the worktree are skipped and logged, never crashing the run.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from gates.finding import Finding, validate_finding

logger = logging.getLogger(__name__)

#: ``- `<file>:<line>` [`<code>`]: <message>`` — the code bracket is optional.
_LINE_RE = re.compile(
    r"^- `(?P<file>[^:`]+):(?P<line>[^`]+)`"
    r"(?: \[`(?P<code>[^`]+)`\])?"
    r": (?P<message>.*)$"
)

#: Gate findings have no explicit tier in the line grammar.
_DEFAULT_SEVERITY = "MAJOR"


def parse_gate_findings(path: Path, worktree_root: Path) -> list[Finding]:
    """Parse ``path`` (a ``gate-findings.md``) into validated findings.

    ``worktree_root`` is resolved once here before containment checks. Lines that
    do not match the grammar are ignored silently; a matched line whose line
    number is non-integer or whose file escapes the worktree is skipped with a
    warning. A missing or unreadable file yields an empty list (logged). Never
    raises. Source order is preserved.
    """
    root = Path(worktree_root).resolve()
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.warning("could not read gate-findings file %s: %s", path, exc)
        return []

    findings: list[Finding] = []
    for raw in text.splitlines():
        m = _LINE_RE.match(raw)
        if m is None:
            continue
        line_str = m.group("line").strip()
        try:
            line = int(line_str)
        except ValueError:
            logger.warning("skipping finding with non-integer line %r: %s", line_str, raw)
            continue
        finding = Finding(
            file=m.group("file").strip(),
            line=line,
            severity=_DEFAULT_SEVERITY,
            code=(m.group("code") or "").strip(),
            message=m.group("message").strip(),
        )
        if not validate_finding(finding, root):
            logger.warning("skipping finding failing validation (containment/line): %s", raw)
            continue
        findings.append(finding)
    return findings
