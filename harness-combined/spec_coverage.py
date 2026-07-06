# harness-combined/spec_coverage.py
"""Spec coverage map: match a ticket's requirements to the specs that cover them.

Parses ``requirements.md`` (FRs + ACs) and the ticket's spec ``.py`` files, matches
each requirement to zero-or-more specs by normalized Jaccard token overlap, and writes
a human-readable ``spec-coverage.md``. Also exposes ``format_build_warning`` so the build
flow can surface uncovered requirements as a non-blocking warning.

Stdlib only (matches memory.py / dag.py / ticket.py). Spec files are parsed with ``ast``
and literal extraction only — never executed. All diagnostics go to stderr; the
machine-consumed result goes to stdout.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DEFAULT_THRESHOLD = 0.5

_FR_HEADER = "## Functional Requirements"
_AC_HEADER = "## Acceptance Criteria"
_NUMBERED_RE = re.compile(r"^\s*\d+\.\s+(.*\S)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class SpecParseError(Exception):
    """Raised when a spec file's ``acceptance_criteria`` is not a list of string literals."""


@dataclass
class Requirement:
    id: str  # "FR-1", "AC-1", ...
    kind: Literal["FR", "AC"]
    text: str


@dataclass
class RequirementMatch:
    requirement: Requirement
    covering_specs: list[str]  # spec IDs
    score: float  # highest Jaccard score among covering specs


@dataclass
class CoverageReport:
    covered: list[RequirementMatch]
    uncovered: list[Requirement]
    threshold: float = DEFAULT_THRESHOLD
    ticket_slug: str = ""
    covered_by: dict[str, list[str]] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Path safety
# --------------------------------------------------------------------------- #
def _resolve_within(path: Path | str, project_root: Path | str) -> Path:
    """Resolve *path* and confirm it stays inside *project_root*; else raise ValueError."""
    root = Path(project_root).resolve()
    resolved = Path(path).resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError(f"path {resolved} escapes project root {root}")
    return resolved


# --------------------------------------------------------------------------- #
# Tokenization / matching
# --------------------------------------------------------------------------- #
def _normalize_tokens(text: str) -> set[str]:
    """Lowercase, strip punctuation, split into a set of tokens (case-insensitive)."""
    return set(_TOKEN_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _section_lines(text: str, header: str) -> list[str] | None:
    """Return the lines under a level-2 *header* up to the next ``## `` header.

    Returns None when the exact header is absent (so callers can warn).
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i + 1
            break
    if start is None:
        return None
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        collected.append(line)
    return collected


def parse_requirements(path: Path | str, project_root: Path | str) -> list[Requirement]:
    """Extract FRs (numbered) and ACs (bullets) from a ticket's requirements.md."""
    req_path = _resolve_within(path, project_root)
    text = req_path.read_text(encoding="utf-8")

    requirements: list[Requirement] = []

    fr_lines = _section_lines(text, _FR_HEADER)
    if fr_lines is None:
        print(
            f"coverage: no '{_FR_HEADER}' section found in {req_path}",
            file=sys.stderr,
        )
    else:
        n = 0
        for line in fr_lines:
            m = _NUMBERED_RE.match(line)
            if m:
                n += 1
                requirements.append(Requirement(id=f"FR-{n}", kind="FR", text=m.group(1)))
        if n == 0:
            print(f"coverage: '{_FR_HEADER}' section has no numbered items", file=sys.stderr)

    ac_lines = _section_lines(text, _AC_HEADER)
    if ac_lines is None:
        print(
            f"coverage: no '{_AC_HEADER}' section found in {req_path}",
            file=sys.stderr,
        )
    else:
        n = 0
        for line in ac_lines:
            m = _BULLET_RE.match(line)
            if m:
                n += 1
                requirements.append(Requirement(id=f"AC-{n}", kind="AC", text=m.group(1)))

    return requirements


def parse_spec_criteria(spec_path: Path | str, project_root: Path | str) -> list[str]:
    """Extract the ``acceptance_criteria`` string literals from a spec .py file.

    Uses ``ast`` only — the spec file is never executed. Raises SpecParseError if the
    criteria list contains a non-string-literal (f-string, comprehension, name, ...).
    """
    resolved = _resolve_within(spec_path, project_root)
    source = resolved.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # spec file itself is malformed
        raise SpecParseError(f"cannot parse {resolved}: {exc}") from exc

    list_node: ast.List | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "acceptance_criteria":
                    if not isinstance(kw.value, ast.List):
                        raise SpecParseError(
                            f"{resolved}: acceptance_criteria must be a list literal"
                        )
                    list_node = kw.value
                    break
        if list_node is not None:
            break

    if list_node is None:
        return []

    criteria: list[str] = []
    for elt in list_node.elts:
        try:
            value = ast.literal_eval(elt)
        except (ValueError, SyntaxError) as exc:
            raise SpecParseError(
                f"{resolved}: acceptance_criteria entries must be string literals "
                f"(got a non-literal expression)"
            ) from exc
        if not isinstance(value, str):
            raise SpecParseError(
                f"{resolved}: acceptance_criteria entries must be strings, got {type(value).__name__}"
            )
        criteria.append(value)
    return criteria


# --------------------------------------------------------------------------- #
# Coverage matching
# --------------------------------------------------------------------------- #
def match_coverage(
    requirements: list[Requirement],
    spec_criteria: dict[str, list[str]],
    threshold: float = DEFAULT_THRESHOLD,
) -> CoverageReport:
    """Match each requirement to the specs whose criteria overlap it >= threshold."""
    covered: list[RequirementMatch] = []
    uncovered: list[Requirement] = []
    covered_by: dict[str, list[str]] = {}

    for req in requirements:
        req_tokens = _normalize_tokens(req.text)
        covering: list[str] = []
        best = 0.0
        for spec_id, criteria in spec_criteria.items():
            spec_best = 0.0
            for crit in criteria:
                spec_best = max(spec_best, _jaccard(req_tokens, _normalize_tokens(crit)))
            if spec_best >= threshold:
                covering.append(spec_id)
                best = max(best, spec_best)
        if covering:
            covered.append(RequirementMatch(requirement=req, covering_specs=covering, score=best))
            covered_by[req.id] = covering
        else:
            uncovered.append(req)

    return CoverageReport(
        covered=covered,
        uncovered=uncovered,
        threshold=threshold,
        covered_by=covered_by,
    )


# --------------------------------------------------------------------------- #
# Rendering / warning
# --------------------------------------------------------------------------- #
def _render_coverage_md(report: CoverageReport) -> str:
    lines: list[str] = ["# Spec Coverage Map", ""]
    if report.ticket_slug:
        lines.append(f"**Ticket**: {report.ticket_slug}")
    lines.append(f"**Threshold**: {report.threshold} (Jaccard token overlap)")
    lines.append("")
    lines.append("| Requirement ID | Kind | Requirement Text | Covering Spec(s) |")
    lines.append("|---|---|---|---|")
    for match in report.covered:
        req = match.requirement
        specs = ", ".join(match.covering_specs)
        text = req.text.replace("|", "\\|")
        lines.append(f"| {req.id} | {req.kind} | {text} | {specs} |")
    for req in report.uncovered:
        text = req.text.replace("|", "\\|")
        lines.append(f"| {req.id} | {req.kind} | {text} | — |")
    lines.append("")
    lines.append("## Uncovered")
    lines.append("")
    if report.uncovered:
        for req in report.uncovered:
            lines.append(f"- {req.id} ({req.kind}): {req.text}")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def write_coverage_map(
    report: CoverageReport, ticket_dir: Path | str, project_root: Path | str
) -> Path:
    """Write (overwrite) spec-coverage.md into ticket_dir. Errors surface (no silent pass)."""
    resolved_dir = _resolve_within(ticket_dir, project_root)
    out_path = resolved_dir / "spec-coverage.md"
    out_path.write_text(_render_coverage_md(report), encoding="utf-8")
    return out_path


def format_build_warning(report: CoverageReport) -> str | None:
    """Return a non-blocking warning listing uncovered requirements, or None if fully covered."""
    if not report.uncovered:
        return None
    header = (
        f"⚠️  Spec coverage: {len(report.uncovered)} requirement(s) have no covering spec:"
    )
    items = [f"  - {req.id} ({req.kind}): {req.text}" for req in report.uncovered]
    return "\n".join([header, *items])


def warning_from_coverage_md(md_text: str) -> str | None:
    """Reconstruct the uncovered warning from a pre-written spec-coverage.md's Uncovered section."""
    section = _section_lines(md_text, "## Uncovered")
    if section is None:
        return None
    uncovered: list[str] = []
    for line in section:
        m = _BULLET_RE.match(line)
        if m:
            uncovered.append(m.group(1))
    if not uncovered:
        return None
    header = f"⚠️  Spec coverage: {len(uncovered)} requirement(s) have no covering spec:"
    items = [f"  - {item}" for item in uncovered]
    return "\n".join([header, *items])


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def build_coverage_map(
    ticket_dir: Path | str,
    specs_dir: Path | str,
    project_root: Path | str,
    threshold: float = DEFAULT_THRESHOLD,
) -> CoverageReport:
    """Read requirements.md + the ticket's spec files and produce a CoverageReport."""
    resolved_ticket = _resolve_within(ticket_dir, project_root)
    resolved_specs = _resolve_within(specs_dir, project_root)
    slug = resolved_ticket.name

    requirements = parse_requirements(resolved_ticket / "requirements.md", project_root)

    spec_criteria: dict[str, list[str]] = {}
    for spec_file in sorted(resolved_specs.glob(f"{slug}-*.py")):
        spec_criteria[spec_file.stem] = parse_spec_criteria(spec_file, project_root)

    report = match_coverage(requirements, spec_criteria, threshold)
    report.ticket_slug = slug
    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _run_warning_only(ticket_dir: Path, project_root: Path) -> int:
    resolved = _resolve_within(ticket_dir, project_root)
    coverage_md = resolved / "spec-coverage.md"
    if not coverage_md.exists():
        return 0  # backward compatible: no map, no warning
    warning = warning_from_coverage_md(coverage_md.read_text(encoding="utf-8"))
    if warning:
        print(warning)
    return 0


def _run_build(ticket_dir: Path, specs_dir: Path, project_root: Path) -> int:
    report = build_coverage_map(ticket_dir, specs_dir, project_root)
    write_coverage_map(report, ticket_dir, project_root)
    print(f"covered={len(report.covered)} uncovered={len(report.uncovered)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or inspect a ticket's spec coverage map.")
    parser.add_argument(
        "--warning-only",
        action="store_true",
        help="Read a pre-written spec-coverage.md and print its uncovered warning (no re-parse).",
    )
    parser.add_argument("paths", nargs="+", help="see usage in the flow docs")
    args = parser.parse_args(argv)

    if args.warning_only:
        if len(args.paths) != 2:
            parser.error("--warning-only takes <ticket_dir> <project_root>")
        ticket_dir, project_root = (Path(p) for p in args.paths)
        return _run_warning_only(ticket_dir, project_root)

    if len(args.paths) != 3:
        parser.error("build mode takes <ticket_dir> <specs_dir> <project_root>")
    ticket_dir, specs_dir, project_root = (Path(p) for p in args.paths)
    return _run_build(ticket_dir, specs_dir, project_root)


if __name__ == "__main__":
    raise SystemExit(main())
