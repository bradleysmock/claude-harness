"""Unit + integration tests for spec_coverage.py (ticket 0014 — spec coverage map)."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

import spec_coverage
from spec_coverage import (
    CoverageReport,
    Requirement,
    SpecParseError,
    build_coverage_map,
    format_build_warning,
    main,
    match_coverage,
    parse_requirements,
    parse_spec_criteria,
    warning_from_coverage_md,
    write_coverage_map,
)

REQ_3FR_2AC = """# Requirements

## Functional Requirements

1. The system must parse requirements markdown.
2. The system must extract acceptance criteria from specs.
3. The system must write a coverage map file.

## Non-Functional Requirements

1. It must be fast.

## Acceptance Criteria

- Given a covered requirement it appears in the table.
- Given an uncovered requirement it appears under Uncovered.
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _spec_file(path: Path, criteria: list[str]) -> Path:
    body = ",\n        ".join(repr(c) for c in criteria)
    src = (
        "from harness import Spec\n\n"
        "spec = Spec(\n"
        "    id='x',\n"
        "    description='d',\n"
        "    constraints=[],\n"
        f"    acceptance_criteria=[\n        {body}\n    ],\n"
        "    target_file='x.py',\n"
        ")\n"
    )
    return _write(path, src)


# --------------------------------------------------------------------------- FR-1
def test_parse_requirements_extracts_frs_and_acs(tmp_path):
    req = _write(tmp_path / "requirements.md", REQ_3FR_2AC)
    reqs = parse_requirements(req, tmp_path)
    frs = [r for r in reqs if r.kind == "FR"]
    acs = [r for r in reqs if r.kind == "AC"]
    assert [r.id for r in frs] == ["FR-1", "FR-2", "FR-3"]
    assert [r.id for r in acs] == ["AC-1", "AC-2"]
    assert frs[0].text == "The system must parse requirements markdown."
    assert acs[1].text == "Given an uncovered requirement it appears under Uncovered."
    # NFR numbered items are NOT captured as FRs
    assert all("fast" not in r.text.lower() for r in reqs)


def test_parse_requirements_nonstandard_header_returns_empty(tmp_path):
    text = REQ_3FR_2AC.replace("## Functional Requirements", "### Functional Requirements")
    req = _write(tmp_path / "requirements.md", text)
    reqs = parse_requirements(req, tmp_path)
    assert [r for r in reqs if r.kind == "FR"] == []


def test_parse_requirements_missing_ac_section(tmp_path):
    text = REQ_3FR_2AC.split("## Acceptance Criteria")[0]
    req = _write(tmp_path / "requirements.md", text)
    reqs = parse_requirements(req, tmp_path)
    assert [r.kind for r in reqs] == ["FR", "FR", "FR"]
    assert not [r for r in reqs if r.kind == "AC"]


# --------------------------------------------------------------------------- FR-2
def test_parse_spec_criteria_extracts_literals(tmp_path):
    spec = _spec_file(tmp_path / "s.py", ["first criterion", "second criterion"])
    assert parse_spec_criteria(spec, tmp_path) == ["first criterion", "second criterion"]


def test_parse_spec_criteria_fstring_raises(tmp_path):
    src = (
        "from harness import Spec\n"
        "name = 'x'\n"
        "spec = Spec(id='x', description='d', constraints=[],\n"
        "    acceptance_criteria=[f'dynamic {name}'], target_file='x.py')\n"
    )
    spec = _write(tmp_path / "s.py", src)
    with pytest.raises(SpecParseError):
        parse_spec_criteria(spec, tmp_path)


def test_parse_spec_criteria_no_keyword_returns_empty(tmp_path):
    src = "from harness import Spec\nspec = Spec(id='x', description='d', constraints=[])\n"
    spec = _write(tmp_path / "s.py", src)
    assert parse_spec_criteria(spec, tmp_path) == []


# --------------------------------------------------------------------------- FR-3
def _reqs(*texts):
    return [Requirement(id=f"FR-{i+1}", kind="FR", text=t) for i, t in enumerate(texts)]


def test_match_exact_hit_covered():
    reqs = _reqs("parse requirements markdown file")
    report = match_coverage(reqs, {"spec-a": ["parse requirements markdown file"]})
    assert report.uncovered == []
    assert report.covered[0].covering_specs == ["spec-a"]
    assert report.covered[0].score == 1.0


def test_match_normalized_hit_covered():
    reqs = _reqs("Parse the File!")
    report = match_coverage(reqs, {"spec-a": ["parse   the file"]})
    assert report.uncovered == []
    assert report.covered[0].score == pytest.approx(1.0)


def test_match_boundary_half_is_covered():
    reqs = _reqs("alpha beta")
    report = match_coverage(reqs, {"spec-a": ["alpha beta gamma delta"]})  # jaccard = 2/4 = 0.5
    assert report.covered and not report.uncovered
    assert report.covered[0].score == pytest.approx(0.5)


def test_match_near_miss_below_threshold_uncovered():
    reqs = _reqs("alpha beta")
    report = match_coverage(reqs, {"spec-a": ["alpha beta gamma delta epsilon"]})  # 2/5 = 0.4
    assert report.uncovered and not report.covered


def test_match_unrelated_uncovered():
    reqs = _reqs("completely different words here")
    report = match_coverage(reqs, {"spec-a": ["nothing shared at all"]})
    assert report.uncovered[0].id == "FR-1"


def test_one_spec_covers_two_requirements():
    reqs = _reqs("parse requirements file", "parse requirements file quickly")
    report = match_coverage(reqs, {"spec-a": ["parse requirements file"]})
    assert len(report.covered) == 2
    assert all("spec-a" in m.covering_specs for m in report.covered)


# --------------------------------------------------------------------------- FR-5
def test_format_build_warning_lists_uncovered():
    report = CoverageReport(
        covered=[],
        uncovered=[
            Requirement("FR-2", "FR", "second req"),
            Requirement("AC-1", "AC", "an ac"),
        ],
    )
    warning = format_build_warning(report)
    assert warning is not None
    assert "FR-2" in warning and "AC-1" in warning
    assert "second req" in warning


def test_format_build_warning_none_when_fully_covered():
    report = CoverageReport(covered=[], uncovered=[])
    assert format_build_warning(report) is None


# --------------------------------------------------------------------------- FR-6
def test_write_coverage_map_overwrites(tmp_path):
    r1 = CoverageReport(covered=[], uncovered=[Requirement("FR-1", "FR", "only first")])
    r2 = CoverageReport(covered=[], uncovered=[Requirement("FR-9", "FR", "only ninth")])
    write_coverage_map(r1, tmp_path, tmp_path)
    write_coverage_map(r2, tmp_path, tmp_path)
    content = (tmp_path / "spec-coverage.md").read_text()
    assert "FR-9" in content and "FR-1 " not in content


def test_write_coverage_map_readonly_raises_oserror(tmp_path):
    ticket_dir = tmp_path / "t"
    ticket_dir.mkdir()
    os.chmod(ticket_dir, stat.S_IRUSR | stat.S_IXUSR)  # read + execute, no write
    try:
        if os.access(ticket_dir, os.W_OK):  # running as root — chmod won't block writes
            pytest.skip("filesystem/user allows write despite chmod")
        report = CoverageReport(covered=[], uncovered=[])
        with pytest.raises(OSError):
            write_coverage_map(report, ticket_dir, tmp_path)
    finally:
        os.chmod(ticket_dir, stat.S_IRWXU)


# --------------------------------------------------------------------------- FR-4 (integration)
def test_build_coverage_map_integration(tmp_path):
    ticket_dir = tmp_path / ".tickets" / "0014-x"
    specs_dir = tmp_path / ".harness" / "specs"
    _write(ticket_dir / "requirements.md", REQ_3FR_2AC)
    # spec covering FR-1 and FR-2 and AC-1, leaving FR-3 and AC-2 uncovered
    _spec_file(
        specs_dir / "0014-x-a.py",
        ["The system must parse requirements markdown."],
    )
    _spec_file(
        specs_dir / "0014-x-b.py",
        [
            "The system must extract acceptance criteria from specs.",
            "Given a covered requirement it appears in the table.",
        ],
    )
    report = build_coverage_map(ticket_dir, specs_dir, tmp_path)
    write_coverage_map(report, ticket_dir, tmp_path)
    md = (ticket_dir / "spec-coverage.md").read_text()

    uncovered_ids = {r.id for r in report.uncovered}
    assert "FR-3" in uncovered_ids and "AC-2" in uncovered_ids
    assert "FR-1" not in uncovered_ids and "AC-1" not in uncovered_ids
    # table + uncovered section present
    assert "| Requirement ID |" in md
    assert "## Uncovered" in md
    assert "FR-3" in md.split("## Uncovered")[1]


def test_build_coverage_map_fully_covered_says_none(tmp_path):
    ticket_dir = tmp_path / ".tickets" / "0014-y"
    specs_dir = tmp_path / ".harness" / "specs"
    _write(ticket_dir / "requirements.md", "## Functional Requirements\n\n1. The system must do the thing.\n")
    _spec_file(specs_dir / "0014-y-a.py", ["The system must do the thing."])
    report = build_coverage_map(ticket_dir, specs_dir, tmp_path)
    assert report.uncovered == []
    write_coverage_map(report, ticket_dir, tmp_path)
    md = (ticket_dir / "spec-coverage.md").read_text()
    assert "None." in md.split("## Uncovered")[1]


# --------------------------------------------------------------------------- Path safety
def test_path_safety_ticket_dir_outside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError):
        build_coverage_map(outside, root / ".harness", root)


def test_path_safety_specs_dir_outside_root(tmp_path):
    root = tmp_path / "root"
    (root / ".tickets" / "0014-x").mkdir(parents=True)
    _write(root / ".tickets" / "0014-x" / "requirements.md", REQ_3FR_2AC)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError):
        build_coverage_map(root / ".tickets" / "0014-x", outside, root)


# --------------------------------------------------------------------------- --warning-only helper
def test_warning_from_coverage_md_roundtrip():
    report = CoverageReport(
        covered=[],
        uncovered=[Requirement("FR-1", "FR", "only requirement")],
        ticket_slug="0014-x",
    )
    md = spec_coverage._render_coverage_md(report)
    warning = warning_from_coverage_md(md)
    assert warning is not None and "FR-1" in warning


def test_warning_from_coverage_md_none_when_covered():
    report = CoverageReport(covered=[], uncovered=[], ticket_slug="0014-x")
    md = spec_coverage._render_coverage_md(report)
    assert warning_from_coverage_md(md) is None


# --------------------------------------------------------------------------- CLI (both modes)
def _sample_ticket(tmp_path):
    ticket_dir = tmp_path / ".tickets" / "0014-x"
    specs_dir = tmp_path / ".harness" / "specs"
    _write(ticket_dir / "requirements.md", REQ_3FR_2AC)
    _spec_file(specs_dir / "0014-x-a.py", ["The system must parse requirements markdown."])
    return ticket_dir, specs_dir


def test_cli_build_mode_writes_map_and_reports_counts(tmp_path, capsys):
    ticket_dir, specs_dir = _sample_ticket(tmp_path)
    rc = main([str(ticket_dir), str(specs_dir), str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "covered=" in out and "uncovered=" in out
    assert (ticket_dir / "spec-coverage.md").exists()


def test_cli_warning_only_prints_uncovered(tmp_path, capsys):
    ticket_dir, specs_dir = _sample_ticket(tmp_path)
    main([str(ticket_dir), str(specs_dir), str(tmp_path)])  # write the map first
    capsys.readouterr()  # drain
    rc = main(["--warning-only", str(ticket_dir), str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    # REQ_3FR_2AC has 5 requirements, only FR-1 covered → warning lists the rest
    assert "no covering spec" in out


def test_cli_warning_only_silent_when_map_absent(tmp_path, capsys):
    # AC-6 backward compatibility: no spec-coverage.md → no output, exit 0
    ticket_dir = tmp_path / ".tickets" / "0014-x"
    ticket_dir.mkdir(parents=True)
    rc = main(["--warning-only", str(ticket_dir), str(tmp_path)])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_cli_warning_only_rejects_wrong_arg_count(tmp_path):
    with pytest.raises(SystemExit):
        main(["--warning-only", str(tmp_path)])  # missing project_root
