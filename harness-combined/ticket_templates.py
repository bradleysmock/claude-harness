"""Per-category template + custom-section building blocks for ``/problem``.

Pure library used by ``commands/problem.md`` to inject per-category templates
(``.tickets/_templates/<category>.md``) and lead-defined custom sections (the
``## Custom Sections`` block in ``.tickets/_standards.md``) into new ticket
artifacts. Every feature is *additive*: when an input is absent the relevant
function returns an empty result and the caller keeps the generic scaffold
unchanged, so a project with neither templates nor custom sections produces
byte-identical output to the pre-feature baseline.

Six components live here:

* :func:`validate_type` — allow-list validator for a caller-supplied ``--type``.
* :func:`load_template` — read a per-category template into section stubs.
* :func:`infer_category` — keyword-heuristic classifier over free text.
* :func:`load_custom_sections` — parse + validate the ``## Custom Sections`` block.
* :func:`merge_sections` — pure additive append of stubs onto a scaffold.
* :func:`enforce_line_limit` — pure per-artifact line-limit truncation.
* :func:`format_type_field` — render the ``status.md`` ``type:`` metadata line.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Canonical category allow-list. ``chore`` and ``docs`` are reserved extension
# points documented in solution.md — intentionally NOT active in this ticket.
CANONICAL_CATEGORIES: tuple[str, ...] = ("bug", "feature", "refactor")

# Case-insensitive union of reserved scaffold headings across the three
# artifacts (see solution.md "Reserved Headings"). A custom stub whose heading
# collides with any of these is dropped. Custom sections are injected into all
# three artifacts, so the exclusion list is the union across all of them.
_RESERVED_HEADINGS_SOURCE: tuple[str, ...] = (
    # problem.md
    "Problem",
    "Impact",
    "Success Criteria",
    "Out of Scope",
    # requirements.md
    "Functional Requirements",
    "Non-Functional Requirements",
    "Tech Stack",
    "Test Strategy",
    "Acceptance Criteria",
    "Open Questions",
    # solution.md
    "Approach",
    "Components",
    "Tech Choices",
    "Test Plan",
    "Tradeoffs",
    "Risks",
    "Implementation Order",
)
RESERVED_HEADINGS: frozenset[str] = frozenset(
    heading.lower() for heading in _RESERVED_HEADINGS_SOURCE
)

# Per-artifact hard line limits, mirroring the scaffold limits in
# commands/problem.md (problem 40, requirements 60, solution 80).
ARTIFACT_LINE_LIMITS: dict[str, int] = {
    "problem.md": 40,
    "requirements.md": 60,
    "solution.md": 80,
}

MAX_CUSTOM_SECTIONS = 5
MAX_STUB_BODY_LINES = 10

# Confidence at or above which an inferred category is trusted; below it the
# result is treated as "no match" and the caller keeps the generic scaffold.
_INFER_THRESHOLD = 0.5

# A scaffold section heading: a level-2 ("## ") markdown heading.
_HEADING_RE = re.compile(r"^## (.+?)\s*$")
# A custom-section stub inside the "## Custom Sections" block: level-3 ("### ").
_STUB_RE = re.compile(r"^### (.+?)\s*$")
# The "## Custom Sections" block marker (case-insensitive).
_CUSTOM_BLOCK_RE = re.compile(r"^##\s+Custom Sections\s*$", re.IGNORECASE)

# Keyword heuristics for category inference. The category with the most keyword
# hits wins; a tie for the top score, or zero hits, means "no match".
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bug": (
        "bug",
        "crash",
        "error",
        "fails",
        "failing",
        "broken",
        "regression",
        "incorrect",
        "exception",
        "defect",
        "wrong",
        "does not work",
        "doesn't work",
    ),
    "feature": (
        "add ",
        "feature",
        "support",
        "implement",
        "introduce",
        "enable",
        "allow ",
        "new ",
        "dark mode",
    ),
    "refactor": (
        "refactor",
        "cleanup",
        "clean up",
        "restructure",
        "rename",
        "simplify",
        "extract",
        "reorganize",
        "decouple",
        "tidy",
    ),
}


def validate_type(raw: str | None) -> str | None:
    """Return the canonical category for ``raw`` or ``None`` if not allow-listed.

    Case-insensitive; returns the lowercase canonical form. Returns ``None`` for
    any value outside :data:`CANONICAL_CATEGORIES` — including path-traversal
    attempts (``"../../escape"``), the reserved ``chore``/``docs`` values, the
    empty string, and ``None``. No filesystem path is ever constructed from an
    unvalidated value.
    """
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().lower()
    if candidate in CANONICAL_CATEGORIES:
        return candidate
    return None


def load_template(
    ticket_type: str, templates_dir: str | Path
) -> list[tuple[str, str]]:
    """Load ``<templates_dir>/<ticket_type>.md`` into ``[(heading, body), ...]``.

    Defense in depth: re-validates ``ticket_type`` against the allow-list
    internally rather than trusting the caller. Returns ``[]`` — never raises —
    when the type is not canonical, the directory or file is absent, the file is
    empty/whitespace-only, or it contains no ``## `` heading. Path containment is
    enforced with ``resolve()`` + ``relative_to`` as a second layer beyond the
    allow-list.
    """
    category = validate_type(ticket_type)
    if category is None:
        logger.warning("load_template: rejected non-canonical type %r", ticket_type)
        return []

    root = Path(templates_dir)
    try:
        target = (root / f"{category}.md").resolve()
        target.relative_to(root.resolve())
    except (ValueError, OSError):
        logger.warning("load_template: path containment failed for type %r", category)
        return []

    if not target.is_file():
        logger.warning("load_template: no template file at %s", target)
        return []

    text = target.read_text(encoding="utf-8")
    if not text.strip():
        logger.warning("load_template: empty template file %s", target)
        return []

    sections = _extract_sections(text)
    if not sections:
        logger.warning("load_template: no '## ' headings in %s", target)
        return []
    return sections


def infer_category(description: str) -> tuple[str | None, float]:
    """Infer a canonical category from free text -> ``(category|None, confidence)``.

    Keyword heuristics over the three canonical categories. No keyword match, or
    an ambiguous tie for the top score, yields ``(None, confidence)`` with a
    confidence below :data:`_INFER_THRESHOLD`. ``chore`` and ``docs`` are reserved
    and are never inferred.
    """
    text = (description or "").lower()
    scores: dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits:
            scores[category] = hits
    if not scores:
        return (None, 0.0)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_category, top_hits = ranked[0]
    total = sum(scores.values())
    confidence = top_hits / total if total else 0.0

    # Ambiguous: another category tied for the top score.
    if len(ranked) > 1 and ranked[1][1] == top_hits:
        return (None, confidence)
    if confidence < _INFER_THRESHOLD:
        return (None, confidence)
    return (top_category, confidence)


def load_custom_sections(standards_path: str | Path) -> list[tuple[str, str]]:
    """Parse the first ``## Custom Sections`` block from ``_standards.md``.

    Returns the accepted ``[(heading, body_stub), ...]``. Only the first
    ``## Custom Sections`` block is honoured; later occurrences are ignored. A
    stub is dropped (with a warning) when its heading collides case-insensitively
    with a reserved scaffold heading or when its body exceeds
    :data:`MAX_STUB_BODY_LINES`; at most :data:`MAX_CUSTOM_SECTIONS` stubs are
    accepted. Returns ``[]`` when the file or the block is absent.
    """
    path = Path(standards_path)
    if not path.is_file():
        return []

    block = _extract_custom_sections_block(path.read_text(encoding="utf-8"))
    if block is None:
        return []

    accepted: list[tuple[str, str]] = []
    for heading, body in _extract_stubs(block):
        if heading.lower() in RESERVED_HEADINGS:
            logger.warning(
                "load_custom_sections: dropped reserved heading %r", heading
            )
            continue
        if len(body.splitlines()) > MAX_STUB_BODY_LINES:
            logger.warning(
                "load_custom_sections: dropped oversized stub %r (> %d lines)",
                heading,
                MAX_STUB_BODY_LINES,
            )
            continue
        if len(accepted) >= MAX_CUSTOM_SECTIONS:
            logger.warning(
                "load_custom_sections: dropped %r (exceeds max %d sections)",
                heading,
                MAX_CUSTOM_SECTIONS,
            )
            continue
        accepted.append((heading, body))
    return accepted


def merge_sections(scaffold: str, sections: list[tuple[str, str]]) -> str:
    """Append ``sections`` after ``scaffold`` and return the merged string.

    Pure (no I/O). Additive only: existing scaffold content is never reordered or
    overwritten — each section is rendered as ``## <heading>`` followed by its
    body and appended after the last scaffold line.
    """
    if not sections:
        return scaffold
    parts = [scaffold.rstrip("\n")]
    for heading, body in sections:
        block = f"## {heading}"
        if body.strip():
            block += f"\n\n{body.strip()}"
        parts.append(block)
    return "\n\n".join(parts) + "\n"


def enforce_line_limit(document: str, limit: int) -> tuple[str, list[str]]:
    """Truncate trailing ``## `` sections until ``document`` fits ``limit`` lines.

    Pure. Returns ``(document, truncated_sections)`` where ``truncated_sections``
    is ALWAYS a list — an empty list when nothing was truncated, never ``None``.
    Injected sections are appended last, so dropping whole trailing ``## ``
    sections removes injected content first. Performs no logging; the caller
    decides how to surface the truncated names.
    """
    truncated: list[str] = []
    lines = document.splitlines()
    if len(lines) <= limit:
        return (document, truncated)

    heading_idxs = [i for i, line in enumerate(lines) if _HEADING_RE.match(line)]
    while len(lines) > limit and heading_idxs:
        start = heading_idxs.pop()
        match = _HEADING_RE.match(lines[start])
        if match is not None:
            truncated.insert(0, match.group(1).strip())
        lines = lines[:start]

    while lines and not lines[-1].strip():
        lines.pop()

    result = "\n".join(lines)
    if document.endswith("\n"):
        result += "\n"
    return (result, truncated)


def format_type_field(category: str | None, inferred: bool) -> str:
    """Render the ``status.md`` ``type:`` line for a ticket category.

    ``type: <category>`` when supplied, ``type: <category> (inferred)`` when
    inferred from the description, and ``type: generic`` when no category applies.
    """
    if category is None:
        return "type: generic"
    if inferred:
        return f"type: {category} (inferred)"
    return f"type: {category}"


def _extract_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into ``[(heading, body), ...]`` on ``## `` headings."""
    return _split_on(text, _HEADING_RE)


def _extract_stubs(block_text: str) -> list[tuple[str, str]]:
    """Split a Custom Sections block into ``[(heading, body), ...]`` on ``### ``."""
    return _split_on(block_text, _STUB_RE)


def _split_on(text: str, heading_re: re.Pattern[str]) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = heading_re.match(line)
        if match:
            if heading is not None:
                sections.append((heading, "\n".join(body).strip("\n")))
            heading = match.group(1).strip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body).strip("\n")))
    return sections


def _extract_custom_sections_block(text: str) -> str | None:
    """Return the text of the first ``## Custom Sections`` block, or ``None``.

    The block spans from the line after ``## Custom Sections`` up to the next
    level-2 (``## ``) heading or end of file. Later ``## Custom Sections`` markers
    are ignored.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _CUSTOM_BLOCK_RE.match(line):
            start = i
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _HEADING_RE.match(line):  # next level-2 section ends the block
            break
        body.append(line)
    return "\n".join(body)
