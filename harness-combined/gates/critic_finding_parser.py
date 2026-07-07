"""Parse critic prose into :class:`~gates.finding.Finding` objects (ticket 0031).

The critic emits findings as::

    **SEVERITY** · <Panel> / <Dimension> · `<file>:<line>`

    <finding body paragraph>

``SEVERITY`` is one of ``BLOCKER``/``MAJOR``/``MINOR``/``OBS``. The ``file:line``
token may appear anywhere in the header (including mid-sentence). A finding with no
``file:line`` — or one whose file escapes the worktree — is *not dropped*; it
degrades to a top-level fallback marker (``file=''``, ``line=None``) so the
orchestrator still posts it as a top-level PR comment. ``code`` is left empty; the
critic dedup key is ``file:line:severity:code`` (stable across non-deterministic
prose), so an empty code is deliberate and consistent.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from gates.finding import Finding, validate_finding

logger = logging.getLogger(__name__)

#: Header line: starts with a bold severity tier.
_HEADER_RE = re.compile(r"^\*\*(?P<sev>BLOCKER|MAJOR|MINOR|OBS)\*\*")

#: First ``file:line`` backtick token anywhere in the header line.
_FILELINE_RE = re.compile(r"`(?P<file>[^:`]+):(?P<line>\d+)`")

_SEVERITIES = frozenset({"BLOCKER", "MAJOR", "MINOR", "OBS"})

#: A Finding Table data row: ``| ID | Severity | Panel | Dimension | Location | Finding |``.
_TABLE_ROW_RE = re.compile(r"^\|(?P<cells>.+)\|\s*$")


def parse_critic_findings(text: str, worktree_root: Path) -> list[Finding]:
    """Parse critic ``text`` into findings, preserving source order.

    Two shapes are supported. When a ``## Finding Table`` is present (the
    ``critique`` skill's ``CRITIQUE.md`` format), *all* severities including
    MINOR/OBS are read from that table — the authoritative punch list. Otherwise
    the ``**SEVERITY** · … · file:line`` block grammar (the ``critic-brief.md``
    format) is used. ``worktree_root`` is resolved once for containment checks.
    Never raises on malformed prose.
    """
    root = Path(worktree_root).resolve()
    table = _parse_finding_table(text, root)
    if table is not None:
        return table
    return _parse_header_blocks(text, root)


def _finalize(file_: str, line_: int | None, severity: str, code: str, message: str, root: Path) -> Finding:
    """Build a Finding, downgrading to a top-level fallback if the file escapes root.

    ``code`` carries the finding's Panel/Dimension classification. The critic dedup
    key is ``file:line:severity:code``, so this discriminates two distinct findings
    that share an anchor and severity (e.g. a Security and a Performance concern on
    the same line) without keying on non-deterministic prose. Panel/Dimension is a
    stable, structural label produced by the panel machinery, not free text.
    """
    if file_:
        probe = Finding(file=file_, line=line_, severity=severity, code=code, message=message)
        if not validate_finding(probe, root):
            logger.warning("critic finding file escapes worktree; using top-level fallback: %s", file_)
            file_, line_ = "", None
    return Finding(file=file_, line=line_, severity=severity, code=code, message=message)


def _parse_finding_table(text: str, root: Path) -> list[Finding] | None:
    """Parse the ``## Finding Table`` rows, or return ``None`` if no table is present."""
    lines = text.splitlines()
    in_table = False
    findings: list[Finding] = []
    saw_table = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.lower().startswith("## finding table"):
            in_table = True
            continue
        if in_table and stripped.startswith("## "):
            break  # next section ends the table
        if not in_table:
            continue
        row = _TABLE_ROW_RE.match(raw.strip())
        if row is None:
            continue
        cells = [c.strip() for c in row.group("cells").split("|")]
        if len(cells) < 6:
            continue
        severity = cells[1].upper()
        if severity not in _SEVERITIES:
            continue  # header row, separator row, or a non-finding row
        saw_table = True
        panel, dimension, location, message = cells[2], cells[3], cells[4], cells[5]
        code = f"{panel} / {dimension}".strip(" /")
        file_, line_ = "", None
        fm = _FILELINE_RE.search(location)
        if fm is not None:
            file_, line_ = fm.group("file").strip(), int(fm.group("line"))
        findings.append(_finalize(file_, line_, severity, code, message, root))
    return findings if saw_table else None


def _parse_header_blocks(text: str, root: Path) -> list[Finding]:
    """Parse the ``**SEVERITY** · … · file:line`` block grammar (critic-brief format)."""
    lines = text.splitlines()
    findings: list[Finding] = []
    i, n = 0, len(lines)
    while i < n:
        header = _HEADER_RE.match(lines[i])
        if header is None:
            i += 1
            continue
        severity = header.group("sev")

        file_ = ""
        line_: int | None = None
        fm = _FILELINE_RE.search(lines[i])
        if fm is not None:
            file_ = fm.group("file").strip()
            line_ = int(fm.group("line"))

        # The middle `·`-delimited segment(s) carry the Panel/Dimension label; use
        # it as the dedup discriminator (deterministic, unlike the prose body).
        segments = [s.strip() for s in lines[i].split("·")]
        code = " · ".join(seg for seg in segments[1:-1] if seg) if len(segments) >= 3 else ""

        # Body runs from the next line up to the following header (or EOF).
        j = i + 1
        body: list[str] = []
        while j < n and _HEADER_RE.match(lines[j]) is None:
            body.append(lines[j])
            j += 1
        message = "\n".join(body).strip()

        findings.append(_finalize(file_, line_, severity, code, message, root))
        i = j
    return findings
