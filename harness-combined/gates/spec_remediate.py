"""Pure spec-remediation fixers for autopilot's score-spec BLOCK interception.

`score-spec` (``context/score-spec.md``) gates a ticket's ``requirements.md`` and
``solution.md`` before a build. In autopilot mode a BLOCK verdict is
auto-remediated rather than bailed back to the lead (``context/spec-remediation.md``,
Step S). This module holds the *structural* fixers and the BLOCK classifier those
steps rely on.

Trust boundary: the text being remediated is the same untrusted artifact text that
score-spec gates, so nothing here authors content designed to pass the gate. Every
function is pure (text in, text out), stdlib only, with no filesystem or network
I/O — the authoritative re-score runs ``score-spec`` itself on the committed files.

The two mechanical fixers are deliberately dumb:

* :func:`append_testplan_row` / :func:`remove_phantom_row` — structural Test Plan
  edits keyed to an FR number; the appended scenario cell cross-references the FR's
  *existing* requirements text, never synthesized prose.
* :func:`substitute_imperative` — literal ``should``/``may``/``could`` -> ``must``
  inside one FR, skipping inline-code spans, with no other rewording.

Anything needing judgement (FR count, placeholders) is classified ``semantic`` and
routed to ``/refine`` by the flow; any BLOCK check this module does not recognise is
classified ``hard_stop`` (fail closed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Classification ────────────────────────────────────────────────────────────

MECHANICAL = "mechanical"
SEMANTIC = "semantic"
HARD_STOP = "hard_stop"

#: score-spec check label -> remediation handling. Keys are the literal check
#: names score-spec prints (``context/score-spec.md`` "Output"). Only the four
#: BLOCK-severity checks need an entry; the WARN-only checks (Implementation Order
#: present, Acceptance criteria) never reach remediation because they never BLOCK.
RECIPE: dict[str, str] = {
    "Test-plan coverage": MECHANICAL,
    "Imperative language": MECHANICAL,
    "FR count": SEMANTIC,
    "No placeholders": SEMANTIC,
}

_REPORT_LINE = re.compile(r"^\s*\[(PASS|WARN|BLOCK)\]\s+(.+?)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FR_ITEM = re.compile(r"^\s*(\d+)\.\s+(.*)$")
#: An ``FR-<n>`` (or ``FR <n>``) reference, never matching the ``FR`` inside
#: ``NFR`` thanks to the negative lookbehind. The digit run keeps trailing
#: ``/<n>`` groups so a combined cell like ``FR-5/9`` yields both numbers.
_FR_REF = re.compile(r"(?<![A-Za-z])FR[-\s]?([\d/]+)", re.IGNORECASE)
_WEAK = re.compile(r"\b(should|may|could)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CheckVerdict:
    """One ``[PASS|WARN|BLOCK] <name>`` line from a score-spec report."""

    name: str
    verdict: str  # "PASS" | "WARN" | "BLOCK"


@dataclass(frozen=True)
class Classification:
    """How each BLOCK check should be handled, bucketed by :data:`RECIPE`."""

    mechanical: list[str]
    semantic: list[str]
    hard_stop: list[str]

    @property
    def must_bail(self) -> bool:
        """True when any BLOCK check is unrecognised — the flow must hard-stop."""
        return bool(self.hard_stop)


def parse_score_report(report: str) -> list[CheckVerdict]:
    """Parse score-spec's structured report into per-check verdicts."""
    verdicts: list[CheckVerdict] = []
    for line in report.splitlines():
        match = _REPORT_LINE.match(line)
        if match:
            verdicts.append(CheckVerdict(name=match.group(2).strip(), verdict=match.group(1)))
    return verdicts


def classify(report: str) -> Classification:
    """Bucket each BLOCK check by :data:`RECIPE`; unknown BLOCK -> hard_stop.

    PASS/WARN checks are ignored — only a BLOCK check needs remediation. An
    unrecognised BLOCK name falls through to ``hard_stop`` so a future score-spec
    check can never be silently skipped (fail closed, FR-6).
    """
    mechanical: list[str] = []
    semantic: list[str] = []
    hard_stop: list[str] = []
    for verdict in parse_score_report(report):
        if verdict.verdict != "BLOCK":
            continue
        handling = RECIPE.get(verdict.name)
        if handling == MECHANICAL:
            mechanical.append(verdict.name)
        elif handling == SEMANTIC:
            semantic.append(verdict.name)
        else:
            hard_stop.append(verdict.name)
    return Classification(mechanical=mechanical, semantic=semantic, hard_stop=hard_stop)


# ── Section / FR parsing ──────────────────────────────────────────────────────


def _section_span(lines: list[str], heading: str) -> tuple[int | None, int | None]:
    """Index range ``[start, end)`` of the body under the first heading whose
    title equals ``heading`` (case-insensitive), up to the next heading of
    equal-or-higher level. ``start`` is the line *after* the heading. Returns
    ``(None, None)`` when the heading is absent.
    """
    start: int | None = None
    start_level = 0
    for i, line in enumerate(lines):
        match = _HEADING.match(line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip().lower()
        if start is None:
            if title == heading.lower():
                start = i + 1
                start_level = level
        elif level <= start_level:
            return (start, i)
    if start is None:
        return (None, None)
    return (start, len(lines))


def _section_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    start, end = _section_span(lines, heading)
    if start is None or end is None:
        return ""
    return "\n".join(lines[start:end])


def _iter_fr_items(section_body: str) -> list[tuple[int, str]]:
    """Yield ``(number, joined_text)`` for each numbered item in a section body.

    A blank line ends the current item; indented lines extend it (wrapped FR
    text). Suited to the contiguous numbered list under ``## Functional
    Requirements``.
    """
    items: list[tuple[int, list[str]]] = []
    current: tuple[int, list[str]] | None = None
    for line in section_body.splitlines():
        match = _FR_ITEM.match(line)
        if match:
            if current is not None:
                items.append(current)
            current = (int(match.group(1)), [match.group(2).strip()])
        elif current is not None and line.startswith((" ", "\t")) and line.strip():
            current[1].append(line.strip())
        elif current is not None and not line.strip():
            items.append(current)
            current = None
    if current is not None:
        items.append(current)
    return [(num, " ".join(parts)) for num, parts in items]


def functional_requirement_numbers(requirements_text: str) -> list[int]:
    """FR numbers declared under ``## Functional Requirements`` (in order)."""
    body = _section_body(requirements_text, "Functional Requirements")
    return [num for num, _ in _iter_fr_items(body)]


def _fr_numbers_in(text: str) -> list[int]:
    nums: list[int] = []
    for raw in _FR_REF.findall(text):
        for part in raw.split("/"):
            if part.isdigit():
                nums.append(int(part))
    return nums


def covered_fr_numbers(solution_text: str) -> list[int]:
    """FR numbers in the *Requirement* column of solution.md's Test Plan table.

    Only the first cell of each table row is inspected, so an FR mentioned in a
    scenario cell does not count as covered (and is not double-counted).
    """
    lines = solution_text.splitlines()
    start, end = _section_span(lines, "Test Plan")
    if start is None or end is None:
        return []
    nums: list[int] = []
    for i in range(start, end):
        line = lines[i]
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        requirement_cell = cells[0] if cells else ""
        nums.extend(_fr_numbers_in(requirement_cell))
    return nums


def get_fr_text(requirements_text: str, fr_number: int) -> str:
    """The existing requirements text for ``fr_number`` (joined to one line)."""
    body = _section_body(requirements_text, "Functional Requirements")
    for num, text in _iter_fr_items(body):
        if num == fr_number:
            return text
    return ""


def uncovered_fr_numbers(requirements_text: str, solution_text: str) -> list[int]:
    """FRs declared in requirements but absent from the Test Plan table."""
    covered = set(covered_fr_numbers(solution_text))
    return [n for n in functional_requirement_numbers(requirements_text) if n not in covered]


def phantom_fr_numbers(requirements_text: str, solution_text: str) -> list[int]:
    """FR numbers referenced in the Test Plan that no requirement declares."""
    declared = set(functional_requirement_numbers(requirements_text))
    seen: list[int] = []
    for n in covered_fr_numbers(solution_text):
        if n not in declared and n not in seen:
            seen.append(n)
    return seen


def _strip_inline_code(text: str) -> str:
    return re.sub(r"`[^`]*`", " ", text)


def nonimperative_fr_numbers(requirements_text: str) -> list[int]:
    """FRs whose prose uses should/may/could (outside inline-code spans)."""
    body = _section_body(requirements_text, "Functional Requirements")
    return [n for n, text in _iter_fr_items(body) if _WEAK.search(_strip_inline_code(text))]


# ── Mechanical fixers ─────────────────────────────────────────────────────────


def _suffix(text: str) -> str:
    return "\n" if text.endswith("\n") else ""


def _fr_line_span(text: str, fr_number: int) -> tuple[int, int] | None:
    """``[start, end)`` line indices for ``fr_number``'s item block, scoped to
    the Functional Requirements section. ``None`` when the FR is absent."""
    lines = text.splitlines()
    sec_start, sec_end = _section_span(lines, "Functional Requirements")
    if sec_start is None or sec_end is None:
        return None
    start: int | None = None
    for i in range(sec_start, sec_end):
        match = _FR_ITEM.match(lines[i])
        if match:
            if int(match.group(1)) == fr_number:
                start = i
            elif start is not None:
                return (start, i)
        elif start is not None and not lines[i].strip():
            return (start, i)
    return (start, sec_end) if start is not None else None


def _match_case(token: str, replacement: str) -> str:
    return replacement.capitalize() if token[:1].isupper() else replacement


def _substitute_weak_outside_code(line: str) -> tuple[str, list[str]]:
    """Replace weak modals with ``must`` outside inline-code spans; return the
    rewritten line and the list of tokens replaced (in order)."""
    parts = re.split(r"(`[^`]*`)", line)
    replaced: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        token = match.group(0)
        replaced.append(token)
        return _match_case(token, "must")

    for j, part in enumerate(parts):
        if j % 2 == 1:  # odd indices are inline-code spans — leave verbatim
            continue
        parts[j] = _WEAK.sub(_sub, part)
    return "".join(parts), replaced


def substitute_imperative(requirements_text: str, fr_number: int) -> tuple[str, str]:
    """Replace should/may/could with ``must`` inside FR ``fr_number`` only.

    Inline-code spans and every other FR are left untouched. Returns
    ``(new_text, announcement)``; ``announcement`` is empty when nothing changed.
    """
    span = _fr_line_span(requirements_text, fr_number)
    if span is None:
        return requirements_text, ""
    lines = requirements_text.splitlines()
    start, end = span
    changed: list[str] = []
    for i in range(start, end):
        new_line, tokens = _substitute_weak_outside_code(lines[i])
        if tokens:
            lines[i] = new_line
            changed.extend(tokens)
    if not changed:
        return requirements_text, ""
    announcement = (
        f"spec-remediate: FR-{fr_number} imperative fix — "
        f"replaced {', '.join(changed)} -> must"
    )
    return "\n".join(lines) + _suffix(requirements_text), announcement


def append_testplan_row(solution_text: str, fr_number: int, fr_text: str) -> tuple[str, str]:
    """Append a structural Test Plan row keyed to ``fr_number``.

    The scenario cell cross-references ``fr_text`` (the FR's existing requirements
    text, passed in verbatim) — no prose is authored here. The Test Type cell is a
    literal ``—`` placeholder, since a structural fix cannot invent a test type.
    Returns ``(new_text, announcement)``.
    """
    lines = solution_text.splitlines()
    start, end = _section_span(lines, "Test Plan")
    if start is None or end is None:
        return solution_text, ""
    last_row: int | None = None
    for i in range(start, end):
        if lines[i].lstrip().startswith("|"):
            last_row = i
    if last_row is None:
        return solution_text, ""
    cell = " ".join(fr_text.split()).replace("|", r"\|")
    row = f"| FR-{fr_number} | — | xref requirements.md FR-{fr_number}: {cell} |"
    lines.insert(last_row + 1, row)
    announcement = (
        f"spec-remediate: appended Test Plan row for FR-{fr_number} "
        f"(cross-ref to requirements.md, no authored prose)"
    )
    return "\n".join(lines) + _suffix(solution_text), announcement


def remove_phantom_row(solution_text: str, fr_number: int) -> tuple[str, str]:
    """Delete Test Plan rows whose Requirement cell references ``fr_number``.

    Only the first (Requirement) cell is inspected, so a row that merely mentions
    the FR in its scenario text is preserved. Returns ``(new_text, announcement)``.
    """
    lines = solution_text.splitlines()
    start, end = _section_span(lines, "Test Plan")
    if start is None or end is None:
        return solution_text, ""
    kept: list[str] = []
    removed = False
    for idx, line in enumerate(lines):
        if start <= idx < end and line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            requirement_cell = cells[0] if cells else ""
            if fr_number in _fr_numbers_in(requirement_cell):
                removed = True
                continue
        kept.append(line)
    if not removed:
        return solution_text, ""
    announcement = (
        f"spec-remediate: removed phantom Test Plan row FR-{fr_number} "
        f"(absent from requirements.md)"
    )
    return "\n".join(kept) + _suffix(solution_text), announcement


def remediate_mechanical(
    requirements_text: str, solution_text: str
) -> tuple[str, str, list[str]]:
    """Apply every mechanical fix in a single pass.

    Order: imperative substitutions (requirements) → append uncovered Test Plan
    rows → remove phantom rows (solution). Returns
    ``(new_requirements, new_solution, announcements)`` with one announcement per
    edit (NFR-1). Detection runs against the post-substitution requirements so an
    appended cross-reference quotes the corrected FR text.
    """
    announcements: list[str] = []
    req = requirements_text
    for n in nonimperative_fr_numbers(req):
        req, note = substitute_imperative(req, n)
        if note:
            announcements.append(note)
    sol = solution_text
    for n in uncovered_fr_numbers(req, sol):
        sol, note = append_testplan_row(sol, n, get_fr_text(req, n))
        if note:
            announcements.append(note)
    for n in phantom_fr_numbers(req, sol):
        sol, note = remove_phantom_row(sol, n)
        if note:
            announcements.append(note)
    return req, sol, announcements
