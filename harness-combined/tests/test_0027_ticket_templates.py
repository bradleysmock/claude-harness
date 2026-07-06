"""Unit tests for ticket_templates.py (ticket 0027 — template customization)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import ticket_templates as tt

# --- validate_type: allow-list + traversal rejection (FR-2a / FR-2b) ----------


@pytest.mark.parametrize("value", ["bug", "BUG", "  Feature  ", "refactor"])
def test_validate_type_accepts_canonical(value: str) -> None:
    assert tt.validate_type(value) == value.strip().lower()


@pytest.mark.parametrize(
    "value", ["../../escape", "chore", "docs", "", "   ", "unknown", None]
)
def test_validate_type_rejects_non_canonical(value: object) -> None:
    assert tt.validate_type(value) is None  # type: ignore[arg-type]  # intentional non-str/None input


# --- load_template: heading extraction (FR-1, FR-6) ---------------------------


def _write_template(tmp_path: Path, name: str, body: str) -> Path:
    templates = tmp_path / "_templates"
    templates.mkdir(exist_ok=True)
    (templates / name).write_text(body, encoding="utf-8")
    return templates


def test_load_template_extracts_sections(tmp_path: Path) -> None:
    templates = _write_template(
        tmp_path,
        "bug.md",
        "## Reproduction Steps\n1. do a thing\n\n## Expected vs Actual\nboom\n",
    )
    sections = tt.load_template("bug", templates)
    headings = [h for h, _ in sections]
    assert "Reproduction Steps" in headings
    assert "Expected vs Actual" in headings
    repro_body = dict(sections)["Reproduction Steps"]
    assert "do a thing" in repro_body


def test_load_template_rejects_traversal_type(tmp_path: Path) -> None:
    # Even if a file exists one level up, an invalid type never resolves a path.
    (tmp_path / "escape.md").write_text("## Escaped\nx\n", encoding="utf-8")
    templates = tmp_path / "_templates"
    templates.mkdir()
    assert tt.load_template("../escape", templates) == []


# --- load_template: empty / missing / unparseable -> [] no crash (FR-7) -------


def test_load_template_empty_file_returns_empty(tmp_path: Path) -> None:
    templates = _write_template(tmp_path, "bug.md", "   \n\n")
    assert tt.load_template("bug", templates) == []


def test_load_template_no_headings_returns_empty(tmp_path: Path) -> None:
    templates = _write_template(tmp_path, "feature.md", "just prose, no headings\n")
    assert tt.load_template("feature", templates) == []


def test_load_template_missing_file_returns_empty(tmp_path: Path) -> None:
    templates = tmp_path / "_templates"
    templates.mkdir()
    assert tt.load_template("refactor", templates) == []


def test_load_template_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert tt.load_template("bug", tmp_path / "does_not_exist") == []


# --- infer_category: bug / feature / refactor + ambiguous (FR-3) --------------


def test_infer_category_bug() -> None:
    category, confidence = tt.infer_category("login page crashes on submit")
    assert category == "bug"
    assert confidence > 0.0


def test_infer_category_feature() -> None:
    category, _ = tt.infer_category("add a dark mode toggle for the dashboard")
    assert category == "feature"


def test_infer_category_refactor() -> None:
    category, _ = tt.infer_category("refactor and simplify the gate runner")
    assert category == "refactor"


def test_infer_category_ambiguous_returns_none() -> None:
    category, confidence = tt.infer_category("the thing over there by the desk")
    assert category is None
    assert confidence < tt._INFER_THRESHOLD


def test_infer_category_never_infers_reserved() -> None:
    category, _ = tt.infer_category("write some docs for a chore task")
    assert category not in {"chore", "docs"}


# --- load_custom_sections: validation (FR-4d, body length, count cap) ---------


def _write_standards(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "_standards.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_custom_sections_drops_reserved_heading(tmp_path: Path) -> None:
    path = _write_standards(
        tmp_path,
        "# Standards\n\n## Custom Sections\n\n"
        "### Problem\nshould be dropped\n\n"
        "### Rollout Plan\nstaged rollout\n",
    )
    sections = tt.load_custom_sections(path)
    headings = [h for h, _ in sections]
    assert "Problem" not in headings
    assert "Rollout Plan" in headings


def test_load_custom_sections_drops_oversized_body(tmp_path: Path) -> None:
    long_body = "\n".join(f"line {i}" for i in range(tt.MAX_STUB_BODY_LINES + 1))
    path = _write_standards(
        tmp_path,
        f"## Custom Sections\n\n### Too Long\n{long_body}\n\n### Fine\nok\n",
    )
    headings = [h for h, _ in tt.load_custom_sections(path)]
    assert "Too Long" not in headings
    assert "Fine" in headings


def test_load_custom_sections_caps_count(tmp_path: Path) -> None:
    stubs = "\n".join(
        f"### Section {i}\nbody {i}" for i in range(tt.MAX_CUSTOM_SECTIONS + 3)
    )
    path = _write_standards(tmp_path, f"## Custom Sections\n\n{stubs}\n")
    assert len(tt.load_custom_sections(path)) == tt.MAX_CUSTOM_SECTIONS


def test_load_custom_sections_absent_block_returns_empty(tmp_path: Path) -> None:
    path = _write_standards(tmp_path, "# Standards\n\n## Engineering\nprose\n")
    assert tt.load_custom_sections(path) == []


def test_load_custom_sections_first_block_wins(tmp_path: Path) -> None:
    path = _write_standards(
        tmp_path,
        "## Custom Sections\n\n### First\na\n\n"
        "## Other\n\n## Custom Sections\n\n### Second\nb\n",
    )
    headings = [h for h, _ in tt.load_custom_sections(path)]
    assert headings == ["First"]


def test_load_custom_sections_missing_file_returns_empty(tmp_path: Path) -> None:
    assert tt.load_custom_sections(tmp_path / "nope.md") == []


# --- merge_sections: additive append (FR-4) -----------------------------------


def test_merge_sections_is_additive() -> None:
    scaffold = "# Problem Statement\n\n## Problem\n\nsomething broke\n"
    merged = tt.merge_sections(scaffold, [("Rollout Plan", "staged")])
    assert "something broke" in merged  # scaffold preserved
    assert "## Rollout Plan" in merged
    assert merged.index("## Problem") < merged.index("## Rollout Plan")


def test_merge_sections_no_sections_is_noop() -> None:
    scaffold = "# Doc\n\n## A\n\nbody\n"
    assert tt.merge_sections(scaffold, []) == scaffold


# --- enforce_line_limit: truncation (NFR-2) -----------------------------------


def test_enforce_line_limit_within_limit_returns_empty() -> None:
    document = "## A\nbody\n"
    result, truncated = tt.enforce_line_limit(document, 40)
    assert truncated == []
    assert result == document


def test_enforce_line_limit_truncates_trailing_sections() -> None:
    base = "\n".join(f"scaffold line {i}" for i in range(35))
    document = tt.merge_sections(
        base, [("Injected One", "x\ny"), ("Injected Two", "z")]
    )
    result, truncated = tt.enforce_line_limit(document, 40)
    assert truncated  # non-empty
    assert "Injected Two" in truncated
    assert len(result.splitlines()) <= 40


# --- format_type_field: supplied / inferred / generic (status.md) -------------


def test_format_type_field_supplied() -> None:
    assert tt.format_type_field("bug", False) == "type: bug"


def test_format_type_field_inferred() -> None:
    assert tt.format_type_field("bug", True) == "type: bug (inferred)"


def test_format_type_field_generic() -> None:
    assert tt.format_type_field(None, False) == "type: generic"


# --- NFR-1: template load with absent _templates/ dir is fast -----------------


def test_load_template_absent_dir_is_fast(tmp_path: Path) -> None:
    absent = tmp_path / "_templates"  # never created
    start = time.perf_counter()
    for _ in range(100):
        assert tt.load_template("bug", absent) == []
    elapsed_ms = (time.perf_counter() - start) * 1000
    # Relaxed CI threshold (NFR-1 documents 10ms local / 50ms CI).
    assert elapsed_ms < 50.0, f"100 iterations took {elapsed_ms:.1f}ms"
