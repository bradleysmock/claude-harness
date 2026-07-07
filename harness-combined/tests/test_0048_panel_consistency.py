"""Consistency guards for the critique panel roster (ticket 0048).

Three properties are pinned as tests so drift becomes a failing build rather than
a review finding:

1. **Bijection** — every panel file referenced by the trigger table in
   ``skills/critique/SKILL.md`` exists on disk, and every panel file on disk
   (except the on-demand Secondary panel) is referenced by the table.
2. **Header discipline** — no panel file carries an independent
   ``*Active when …*`` file-pattern activation sentence; every panel header
   defers to the trigger table as the single activation source.
3. **New panels present** — the GraphQL, gRPC/Protobuf, and .NET panels exist in
   the house format and each has a trigger-table row (FR-1..FR-3).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PANELS_DIR = ROOT / "context" / "panels"
SKILL = ROOT / "skills" / "critique" / "SKILL.md"

# The Secondary panel is deliberately NOT in the trigger table: it is loaded on
# demand only when the primary panels reach an impasse (SKILL.md Step 2). Exclude
# it from the "every panel is referenced by the table" direction of the bijection.
NOT_IN_TABLE = {"secondary.md"}

NEW_PANELS = {"graphql.md", "grpc-protobuf.md", "dotnet.md"}

# A panel file reference in the trigger table, e.g.
# `${CLAUDE_PLUGIN_ROOT}/context/panels/python.md`. Hyphens appear (grpc-protobuf).
_PANEL_REF = re.compile(r"context/panels/([A-Za-z0-9_-]+\.md)")
# The drifted activation wording this ticket removes.
_ACTIVE_WHEN = re.compile(r"^\s*\*?\s*Active when", re.IGNORECASE)
# File-pattern activation text: a bare `**/` glob, or a backtick-delimited glob
# *token* — a spaceless backtick span containing a `*` (e.g. `**/*.py`,
# `*.graphql`, `*.{yaml,json}`). Requiring the span to be spaceless keeps it from
# swallowing prose between a `skills/critique/SKILL.md` reference and a later
# backtick (markdown emphasis `*` lives in that prose). Panel cross-references
# like `graphql.md` have no `*`, so they are not flagged. Enforces FR-4's
# "no file-pattern activation text remains" beyond the exact `Active when` form.
_FILE_PATTERN = re.compile(r"\*\*/|`[^`\s]*\*[^`\s]*`")
# How many leading lines constitute a panel's header block (title + blank +
# activation/deferral line, with slack). Header-discipline checks anchor here so
# a stray reference deep in a hazard table cannot satisfy or trip them.
_HEADER_LINES = 6


def _header(panel: str) -> str:
    return "\n".join((PANELS_DIR / panel).read_text().splitlines()[:_HEADER_LINES])


def _panel_files() -> set[str]:
    return {p.name for p in PANELS_DIR.glob("*.md")}


def _table_referenced_panels() -> set[str]:
    """Panel basenames referenced from the trigger-table rows only.

    Restrict to markdown table rows (lines starting with ``|``) so prose
    references elsewhere in SKILL.md — e.g. the on-demand mention of
    ``secondary.md`` in Step 2 — do not count as table activation.
    """
    referenced: set[str] = set()
    for line in SKILL.read_text().splitlines():
        if not line.lstrip().startswith("|"):
            continue
        referenced.update(_PANEL_REF.findall(line))
    return referenced


def test_skill_and_panels_exist() -> None:
    assert SKILL.is_file(), f"missing critique skill at {SKILL}"
    assert PANELS_DIR.is_dir(), f"missing panels dir at {PANELS_DIR}"


def test_every_referenced_panel_exists() -> None:
    referenced = _table_referenced_panels()
    files = _panel_files()
    missing = sorted(referenced - files)
    assert not missing, f"trigger table references non-existent panel files: {missing}"


def test_every_panel_is_referenced() -> None:
    referenced = _table_referenced_panels()
    files = _panel_files()
    orphaned = sorted(files - referenced - NOT_IN_TABLE)
    assert not orphaned, (
        f"panel files exist but no trigger-table row references them: {orphaned}"
    )


@pytest.mark.parametrize("panel", sorted(_panel_files()))
def test_no_independent_activation_wording(panel: str) -> None:
    text = (PANELS_DIR / panel).read_text()
    offenders = [ln for ln in text.splitlines() if _ACTIVE_WHEN.match(ln)]
    assert not offenders, (
        f"{panel} still carries independent activation wording (must defer to the "
        f"trigger table): {offenders}"
    )
    # Beyond the exact prior `Active when` phrasing, no file-pattern activation
    # text (globs, backtick extension patterns) may live in the header block —
    # otherwise drift could reappear in a different shape and still pass.
    header = _header(panel)
    patterns = _FILE_PATTERN.findall(header)
    assert not patterns, (
        f"{panel} header carries file-pattern activation text (activation belongs "
        f"only in the trigger table): {patterns}"
    )


@pytest.mark.parametrize("panel", sorted(_panel_files()))
def test_header_defers_to_trigger_table(panel: str) -> None:
    assert "skills/critique/SKILL.md" in _header(panel), (
        f"{panel}'s header block does not name the trigger table in "
        f"skills/critique/SKILL.md as its activation source"
    )


@pytest.mark.parametrize("panel", sorted(NEW_PANELS))
def test_new_panel_exists_and_referenced(panel: str) -> None:
    assert (PANELS_DIR / panel).is_file(), f"expected new panel {panel} to exist"
    assert panel in _table_referenced_panels(), (
        f"new panel {panel} is not referenced by the trigger table"
    )


@pytest.mark.parametrize("panel", sorted(NEW_PANELS))
def test_new_panel_house_format(panel: str) -> None:
    """New panels follow the house format (NFR-1): a '## <Name> Panel' header,
    named experts with positions tables, a '## Review Dimensions' section with a
    numbered dimension carrying a hazard table, and a length of 40-90 lines."""
    text = (PANELS_DIR / panel).read_text()
    lines = text.splitlines()
    assert lines[0].startswith("## ") and lines[0].rstrip().endswith("Panel"), (
        f"{panel} first line is not a '## <Name> Panel' header: {lines[0]!r}"
    )
    assert "## Review Dimensions" in text, f"{panel} lacks a Review Dimensions section"
    assert re.search(r"^### Dimension \d+", text, re.MULTILINE), (
        f"{panel} lacks a numbered '### Dimension N' block"
    )
    # Named experts with a positions table, and a dimension hazard table — the two
    # markdown tables the house format requires (NFR-1).
    assert "| Position | What it means in practice |" in text, (
        f"{panel} lacks a named-expert positions table"
    )
    assert re.search(r"^\|\s*Hazard\s*\|", text, re.MULTILINE), (
        f"{panel} lacks a dimension hazard table"
    )
    n = len(lines)
    assert 40 <= n <= 90, f"{panel} is {n} lines; house format requires 40-90"
