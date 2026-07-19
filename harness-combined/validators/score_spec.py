#!/usr/bin/env python3
"""Deterministic mechanical checks 1-6 from ``context/score-spec.md``.

This is a **CLI module** mirroring ``standards_validator.py``'s conventions: a
pure ``score(requirements_text, solution_text)`` seam for the six mechanical,
regex-decidable score-spec checks (FR count, imperative language, test-plan
coverage, Implementation Order present, no placeholders, acceptance criteria),
plus a ``main()`` CLI that reads a ticket directory, prints the standard
``score-spec:`` report block, and exits 0/1/2 for PASS/WARN/BLOCK.

Check 7 (FR testability) is judged, not mechanical — this module never emits
it. ``context/score-spec.md`` directs consumers to run this CLI for checks 1-6
and insert their own judged testability line above the verdict before
recomputing the final verdict.

Check 3's Test-Plan-table side reuses ``gates/spec_remediate.py``'s
``covered_fr_numbers`` directly (loaded via
``importlib.util.spec_from_file_location`` against the sibling file path,
never a package import of ``gates``, whose ``__init__.py`` runs unrelated
``models``/``tomli`` imports) so a Test Plan row this validator accepts is
parsed identically to what autopilot's Step S remediation
(``append_testplan_row``/``remove_phantom_row``) targets. The load is lazy
(triggered on first use, from inside ``main()``'s try block) so a load
failure exits 2 with a reason on stderr rather than a traceback at import
time.

Checks 1-3's *requirements.md* side (which FR numbers exist, and their text)
is parsed by a **local** top-level-items helper rather than
``spec_remediate``'s own ``functional_requirement_numbers``/
``nonimperative_fr_numbers``: ``spec_remediate``'s item parser treats any
indented numbered line as a new item (it exists to drive line-level
remediation edits, not to count FRs), so a nested numbered sub-list inside
an FR would otherwise be mistaken for — and its text checked as — a second,
competing top-level FR. score-spec's own FR-1 already requires top-level-only
scoping for the count; using the same parser for checks 2-3 keeps all three
requirements.md-side checks consistent instead of only check 1 being immune
to nested sub-lists.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

# --- check labels — byte-identical to context/score-spec.md's Output block ---

CHECK_FR_COUNT = "FR count"
CHECK_IMPERATIVE = "Imperative language"
CHECK_TESTPLAN = "Test-plan coverage"
CHECK_IMPL_ORDER = "Implementation Order present"
CHECK_PLACEHOLDERS = "No placeholders"
CHECK_ACCEPTANCE = "Acceptance criteria"

MIN_FR_COUNT = 3
MIN_ACCEPTANCE_BULLETS = 2

_EXIT_CODES = {"PASS": 0, "WARN": 1, "BLOCK": 2}


@dataclass(frozen=True)
class CheckResult:
    """One ``[PASS|WARN|BLOCK] <name>`` line, with optional detail sub-lines."""

    name: str
    verdict: str  # "PASS" | "WARN" | "BLOCK"
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoreReport:
    """The six mechanical :class:`CheckResult`\\ s, in score-spec.md's Output order."""

    checks: tuple[CheckResult, ...]

    @property
    def verdict(self) -> str:
        verdicts = {c.verdict for c in self.checks}
        if "BLOCK" in verdicts:
            return "BLOCK"
        if "WARN" in verdicts:
            return "WARN"
        return "PASS"


# --- containment (McGraw containment, mirrors standards_validator.py) --------


def _resolve_contained(path: str | Path, root: Path) -> Path:
    """Resolve ``path`` and verify it stays within ``root``."""
    candidate = Path(path)
    resolved = (
        candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    )
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"path escapes project root: {path!r}") from None
    return resolved


# --- spec_remediate reuse (check 3's Test-Plan-table side) --------------------

_MODULE_ROOT = Path(__file__).resolve().parent.parent

_spec_remediate: ModuleType | None = None


def _load_spec_remediate() -> ModuleType:
    path = _resolve_contained(_MODULE_ROOT / "gates" / "spec_remediate.py", _MODULE_ROOT)
    module_spec = importlib.util.spec_from_file_location("_score_spec_remediate", path)
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"cannot load spec_remediate module from {path}")
    module = importlib.util.module_from_spec(module_spec)
    # Register before exec: spec_remediate.py's frozen dataclasses combined
    # with `from __future__ import annotations` need `sys.modules[__module__]`
    # resolvable *during* class definition (dataclasses' KW_ONLY sentinel
    # check), or class creation raises AttributeError on a None lookup.
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


def _spec_remediate_module() -> ModuleType:
    """Load-and-cache on first use (module-level singleton). Deferred rather
    than run at import time so a load failure (missing file, bad containment)
    surfaces through main()'s fail-closed try/except (FR-7) instead of an
    uncaught traceback at import."""
    global _spec_remediate
    if _spec_remediate is None:
        _spec_remediate = _load_spec_remediate()
    return _spec_remediate


# --- checks 1-3: requirements.md-side parsing (local, top-level-only) ---------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_TOP_LEVEL_FR_ITEM_RE = re.compile(r"^(\d+)\.\s+(.*)$")  # no leading `\s*` — top-level only
# Unlike _TOP_LEVEL_FR_ITEM_RE, these two allow any indentation: checks 4/5
# only need to know an ordered/bulleted item exists somewhere in the section
# (presence, not a per-item count keyed to a specific FR number), so a nested
# list item counts the same as a top-level one here.
_ORDERED_ITEM_RE = re.compile(r"^\s*\d+\.\s+\S")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+\S")
_WEAK_MODAL_RE = re.compile(r"\b(should|may|could)\b", re.IGNORECASE)


def _section_body_lines(text: str, heading: str) -> list[str]:
    """Lines under the first heading matching ``heading`` (case-insensitive),
    up to the next heading of equal-or-higher level."""
    lines = text.splitlines()
    start: int | None = None
    start_level = 0
    end = len(lines)
    for i, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip().lower()
        if start is None:
            if title == heading.lower():
                start = i + 1
                start_level = level
        elif level <= start_level:
            end = i
            break
    if start is None:
        return []
    return lines[start:end]


def _top_level_fr_items(requirements_text: str) -> list[tuple[int, str]]:
    """Top-level (unindented) numbered items under ``## Functional
    Requirements``, in order, with indented continuation lines folded into
    the owning item's text.

    Unlike ``spec_remediate._iter_fr_items`` (which matches a numbered line
    at *any* indentation as a new item), an indented numbered line here is
    treated as part of the current item's wrapped text — so a nested
    numbered sub-list is never mistaken for a second, competing FR.
    """
    body = _section_body_lines(requirements_text, "Functional Requirements")
    items: list[tuple[int, list[str]]] = []
    current: tuple[int, list[str]] | None = None
    for line in body:
        match = _TOP_LEVEL_FR_ITEM_RE.match(line)
        if match:
            if current is not None:
                items.append(current)
            current = (int(match.group(1)), [match.group(2).strip()])
        elif current is not None and line.strip():
            current[1].append(line.strip())
        elif current is not None and not line.strip():
            items.append(current)
            current = None
    if current is not None:
        items.append(current)
    return [(num, " ".join(parts)) for num, parts in items]


def _check_fr_count(requirements_text: str) -> CheckResult:
    count = len(_top_level_fr_items(requirements_text))
    if count < MIN_FR_COUNT:
        detail = f"only {count} functional requirement(s); need at least {MIN_FR_COUNT}"
        return CheckResult(CHECK_FR_COUNT, "BLOCK", (detail,))
    return CheckResult(CHECK_FR_COUNT, "PASS")


def _check_imperative(requirements_text: str) -> CheckResult:
    flagged = [
        n
        for n, text in _top_level_fr_items(requirements_text)
        if _WEAK_MODAL_RE.search(_mask_inline_code(text))
    ]
    if flagged:
        details = tuple(f"FR-{n}: weak modal (should/may/could)" for n in flagged)
        return CheckResult(CHECK_IMPERATIVE, "BLOCK", details)
    return CheckResult(CHECK_IMPERATIVE, "PASS")


def _check_testplan(requirements_text: str, solution_text: str) -> CheckResult:
    declared = {n for n, _ in _top_level_fr_items(requirements_text)}
    covered = set(_spec_remediate_module().covered_fr_numbers(solution_text))
    uncovered = sorted(n for n in declared if n not in covered)
    phantom = sorted(n for n in covered if n not in declared)
    if uncovered or phantom:
        details = tuple(f"FR-{n}: missing from Test Plan" for n in uncovered) + tuple(
            f"FR-{n}: referenced in Test Plan but not declared in requirements.md"
            for n in phantom
        )
        return CheckResult(CHECK_TESTPLAN, "BLOCK", details)
    return CheckResult(CHECK_TESTPLAN, "PASS")


def _check_impl_order(solution_text: str) -> CheckResult:
    body = _section_body_lines(solution_text, "Implementation Order")
    items = [line for line in body if _ORDERED_ITEM_RE.match(line)]
    if not items:
        detail = "`## Implementation Order` section is missing or has no ordered items"
        return CheckResult(CHECK_IMPL_ORDER, "WARN", (detail,))
    return CheckResult(CHECK_IMPL_ORDER, "PASS")


def _check_acceptance(requirements_text: str) -> CheckResult:
    body = _section_body_lines(requirements_text, "Acceptance Criteria")
    bullets = [line for line in body if _BULLET_RE.match(line)]
    if len(bullets) < MIN_ACCEPTANCE_BULLETS:
        detail = (
            f"only {len(bullets)} acceptance criteria bullet(s); "
            f"need at least {MIN_ACCEPTANCE_BULLETS}"
        )
        return CheckResult(CHECK_ACCEPTANCE, "WARN", (detail,))
    return CheckResult(CHECK_ACCEPTANCE, "PASS")


# --- check 5: no placeholders (fence-aware, inline-code-exempt scanner) -------

_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_BARE_KEYWORD_RE = re.compile(
    r"(?<![A-Za-z0-9])(TODO|TBD|FIXME|XXX)(?![A-Za-z0-9])|\?\?\?", re.IGNORECASE
)
# Requires an internal space so single-token template variables in docs (e.g.
# `<slug>` in a path like `.tickets/XXXX-<slug>/status.md`) are never
# flagged; only multi-word bracketed prose (e.g. `<Bullet list: what must be
# true.>`) reads as an unfilled placeholder.
_BRACKET_RE = re.compile(r"<[^<>\n]*\s[^<>\n]*>")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


@dataclass(frozen=True)
class _Placeholder:
    file: str
    line: int
    column: int
    span: str


def _mask_inline_code(line: str) -> str:
    """Blank out inline single-backtick spans, preserving column offsets, so
    the bare-keyword/bracket scanners skip them."""
    return _INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def _is_stub_table_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    inner = stripped.strip("|")
    if not inner.strip():
        return False
    cells = [c.strip() for c in inner.split("|")]
    return all(c == "..." for c in cells)


def _find_placeholders(text: str, file_label: str) -> list[_Placeholder]:
    lines = text.splitlines()
    fence_idxs = [i for i, line in enumerate(lines) if _FENCE_RE.match(line)]
    if len(fence_idxs) % 2 == 1:
        # An unclosed trailing fence never toggles — its content (and the
        # marker line itself) is scanned as unfenced (fail closed).
        fence_idxs = fence_idxs[:-1]
    fence_set = set(fence_idxs)

    hits: list[_Placeholder] = []
    in_fence = False
    for i, raw_line in enumerate(lines):
        if i in fence_set:
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scan_line = _mask_inline_code(raw_line)
        for m in _BARE_KEYWORD_RE.finditer(scan_line):
            hits.append(_Placeholder(file_label, i + 1, m.start() + 1, m.group(0)))
        for m in _BRACKET_RE.finditer(scan_line):
            hits.append(_Placeholder(file_label, i + 1, m.start() + 1, m.group(0)))
        if _is_stub_table_row(raw_line):
            hits.append(_Placeholder(file_label, i + 1, 1, raw_line.strip()))
    return hits


def _check_placeholders(requirements_text: str, solution_text: str) -> CheckResult:
    hits = _find_placeholders(requirements_text, "requirements.md") + _find_placeholders(
        solution_text, "solution.md"
    )
    if hits:
        details = tuple(f"{h.file}:{h.line}:{h.column}: {h.span!r}" for h in hits)
        return CheckResult(CHECK_PLACEHOLDERS, "BLOCK", details)
    return CheckResult(CHECK_PLACEHOLDERS, "PASS")


# --- the pure seam -------------------------------------------------------------


def score(requirements_text: str, solution_text: str) -> ScoreReport:
    """Score ``requirements_text``/``solution_text`` against checks 1-6.

    Pure: takes only text, performs no file I/O. Returns checks in
    ``context/score-spec.md``'s documented Output order.
    """
    checks = (
        _check_fr_count(requirements_text),
        _check_imperative(requirements_text),
        _check_testplan(requirements_text, solution_text),
        _check_impl_order(solution_text),
        _check_placeholders(requirements_text, solution_text),
        _check_acceptance(requirements_text),
    )
    return ScoreReport(checks=checks)


# --- CLI -----------------------------------------------------------------------


def _format_report(slug: str, report: ScoreReport) -> str:
    lines = [f"score-spec: {slug}", ""]
    for check in report.checks:
        lines.append(f"[{check.verdict}] {check.name}")
        for detail in check.details:
            lines.append(f"  - {detail}")
    lines.append("")
    lines.append(f"Verdict: {report.verdict}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0/1/2 for PASS/WARN/BLOCK; 2 on any failure.

    Argparse usage errors (missing/unknown arguments) raise ``SystemExit(2)``
    from within ``parse_args`` itself — that propagates unhandled, which is
    the documented, deliberate exit-2 behavior for misuse.
    """
    parser = argparse.ArgumentParser(prog="score_spec.py")
    parser.add_argument(
        "ticket_dir", help="path to a ticket directory containing requirements.md and solution.md"
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        root = Path.cwd().resolve()
        ticket_dir = _resolve_contained(args.ticket_dir, root)
        requirements_text = (ticket_dir / "requirements.md").read_text(encoding="utf-8")
        solution_text = (ticket_dir / "solution.md").read_text(encoding="utf-8")
        report = score(requirements_text, solution_text)
    except (OSError, ValueError, LookupError, TypeError, ImportError) as exc:
        # Missing/unreadable artifacts, a path that escaped the project root,
        # or an internal scoring error: halt cleanly with a one-line reason
        # on stderr instead of a traceback (fail closed, FR-7).
        sys.stderr.write(f"score-spec could not run: {exc}\n")
        return 2

    slug = ticket_dir.name
    print(_format_report(slug, report))
    return _EXIT_CODES[report.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
