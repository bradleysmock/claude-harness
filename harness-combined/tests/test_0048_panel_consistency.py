"""Consistency guards for the critique panel roster (tickets 0048, 0057).

Rewritten for 0057: activation moved from a prose table in
``skills/critique/SKILL.md`` to canonical TOML data in
``context/panels/triggers.md``. Three properties are pinned as tests so
drift becomes a failing build rather than a review finding:

1. **Bijection** — every panel referenced by ``triggers.md`` exists on disk,
   and every panel file on disk (except Core, always active, and Secondary,
   loaded on demand) is referenced by ``triggers.md``.
2. **Header discipline** — no panel file carries an independent
   ``*Active when …*`` file-pattern activation sentence; every panel header
   defers to ``triggers.md`` as the single activation source.
3. **New panels present** — the GraphQL, gRPC/Protobuf, and .NET panels exist
   in the house format and each has a ``triggers.md`` entry (0048 FR-1..FR-3).
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PANELS_DIR = ROOT / "context" / "panels"
TRIGGERS = PANELS_DIR / "triggers.md"

sys.path.insert(0, str(ROOT))
import panel_detect  # noqa: E402

# Core is always active with no triggers.md entry; Secondary is loaded on
# demand and deliberately excluded (see triggers.md preamble); triggers.md
# itself lives in the panels dir but is not a panel.
NOT_IN_TABLE = {"core.md", "secondary.md", "triggers.md"}

NEW_PANELS = {"graphql.md", "grpc-protobuf.md", "dotnet.md"}

_ACTIVE_WHEN = re.compile(r"^\s*\*?\s*Active when", re.IGNORECASE)
_FILE_PATTERN = re.compile(r"\*\*/|`[^`\s]*\*[^`\s]*`")
_HEADER_LINES = 6


def _header(panel: str) -> str:
    return "\n".join((PANELS_DIR / panel).read_text().splitlines()[:_HEADER_LINES])


def _panel_files() -> set[str]:
    return {p.name for p in PANELS_DIR.glob("*.md")} - {"triggers.md"}


def _table_referenced_panels() -> set[str]:
    specs = panel_detect.load_triggers(TRIGGERS)
    return {spec.file for spec in specs.values()}


def test_skill_and_panels_exist() -> None:
    assert TRIGGERS.is_file(), f"missing trigger data at {TRIGGERS}"
    assert PANELS_DIR.is_dir(), f"missing panels dir at {PANELS_DIR}"


def test_every_referenced_panel_exists() -> None:
    referenced = _table_referenced_panels()
    files = _panel_files()
    missing = sorted(referenced - files)
    assert not missing, f"triggers.md references non-existent panel files: {missing}"


def test_every_panel_is_referenced() -> None:
    referenced = _table_referenced_panels()
    files = _panel_files()
    orphaned = sorted(files - referenced - NOT_IN_TABLE)
    assert not orphaned, (
        f"panel files exist but no triggers.md entry references them: {orphaned}"
    )


@pytest.mark.parametrize("panel", sorted(_panel_files()))
def test_no_independent_activation_wording(panel: str) -> None:
    text = (PANELS_DIR / panel).read_text()
    offenders = [ln for ln in text.splitlines() if _ACTIVE_WHEN.match(ln)]
    assert not offenders, (
        f"{panel} still carries independent activation wording (must defer to "
        f"triggers.md): {offenders}"
    )
    header = _header(panel)
    patterns = _FILE_PATTERN.findall(header)
    assert not patterns, (
        f"{panel} header carries file-pattern activation text (activation belongs "
        f"only in triggers.md): {patterns}"
    )


@pytest.mark.parametrize("panel", sorted(_panel_files()))
def test_header_defers_to_trigger_table(panel: str) -> None:
    assert "context/panels/triggers.md" in _header(panel), (
        f"{panel}'s header block does not name triggers.md as its activation source"
    )


@pytest.mark.parametrize("panel", sorted(NEW_PANELS))
def test_new_panel_exists_and_referenced(panel: str) -> None:
    assert (PANELS_DIR / panel).is_file(), f"expected new panel {panel} to exist"
    assert panel in _table_referenced_panels(), (
        f"new panel {panel} has no triggers.md entry"
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
    assert "| Position | What it means in practice |" in text, (
        f"{panel} lacks a named-expert positions table"
    )
    assert re.search(r"^\|\s*Hazard\s*\|", text, re.MULTILINE), (
        f"{panel} lacks a dimension hazard table"
    )
    n = len(lines)
    assert 40 <= n <= 90, f"{panel} is {n} lines; house format requires 40-90"
