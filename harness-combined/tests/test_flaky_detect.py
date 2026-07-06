"""Unit + integration tests for the test flakiness detector (flaky_detect.py).

Unit tests mock the pytest subprocess (``_run_pytest_once``) so no real suite is
launched: they cover per-run parsing, N-times invocation, the flaky definition
(mixed vs consistent outcomes), threshold exclusion, ranking, path containment, and
the fail-closed annotation contract. Integration tests exercise the JSON/Markdown
serialization round-trip on a real temp directory.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import flaky_detect
from flaky_detect import (
    FlakyReport,
    FlakyTest,
    annotate_failures,
    load_report,
    run_detection,
    write_reports,
)


def _pytest_output(outcomes: dict[str, bool]) -> str:
    """Render fake pytest ``-v`` output for a nodeid -> passed mapping."""
    lines = []
    for i, (node, passed) in enumerate(outcomes.items()):
        status = "PASSED" if passed else "FAILED"
        pct = int(100 * (i + 1) / len(outcomes))
        lines.append(f"{node} {status}                     [{pct:>3}%]")
    return "\n".join(lines) + "\n"


def _mock_runs(monkeypatch: pytest.MonkeyPatch, per_run: list[dict[str, bool]]) -> list[Path]:
    """Patch ``_run_pytest_once`` to yield one canned output per call.

    Returns the list of directories it was called with, for call-count assertions.
    """
    calls: list[Path] = []
    outputs = iter(_pytest_output(o) for o in per_run)

    def fake(directory: Path, timeout: int = 300) -> str:
        calls.append(directory)
        return next(outputs)

    monkeypatch.setattr(flaky_detect, "_run_pytest_once", fake)
    return calls


# ── parsing ───────────────────────────────────────────────────────────────────


def test_parse_run_reads_passed_and_failed() -> None:
    out = _pytest_output({"t.py::a": True, "t.py::b": False})
    parsed = flaky_detect._parse_run(out)
    assert parsed == {"t.py::a": True, "t.py::b": False}


def test_parse_run_treats_error_as_failure() -> None:
    parsed = flaky_detect._parse_run("t.py::a ERROR   [100%]\n")
    assert parsed == {"t.py::a": False}


# ── N-times invocation ──────────────────────────────────────────────────────────


def test_run_detection_invokes_suite_runs_times(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _mock_runs(monkeypatch, [{"t.py::a": True}] * 5)
    run_detection(tmp_path, runs=5, project_root=tmp_path)
    assert len(calls) == 5


def test_run_detection_honors_runs_argument(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _mock_runs(monkeypatch, [{"t.py::a": True}] * 10)
    run_detection(tmp_path, runs=10, project_root=tmp_path)
    assert len(calls) == 10


# ── flaky definition ────────────────────────────────────────────────────────────


def test_mixed_outcome_test_is_flaky_with_pass_rate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # test_a passes 3 of 5 runs -> flaky, "3/5 passed".
    per_run = [{"t.py::test_a": p} for p in (True, False, True, False, True)]
    _mock_runs(monkeypatch, per_run)
    report = run_detection(tmp_path, runs=5, project_root=tmp_path)
    assert len(report.tests) == 1
    assert report.tests[0].name == "t.py::test_a"
    assert report.tests[0].display == "3/5 passed"


def test_consistent_all_fail_is_not_flaky(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_runs(monkeypatch, [{"t.py::broken": False}] * 5)
    report = run_detection(tmp_path, runs=5, project_root=tmp_path)
    assert report.tests == []


def test_consistent_all_pass_is_not_flaky(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_runs(monkeypatch, [{"t.py::stable": True}] * 5)
    report = run_detection(tmp_path, runs=5, project_root=tmp_path)
    assert report.tests == []


# ── threshold ───────────────────────────────────────────────────────────────────


def test_threshold_excludes_test_below_floor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 3/5 -> pass_rate 0.6; threshold 0.8 -> 0.6 < 0.8 -> excluded (treated as blocker).
    per_run = [{"t.py::test_a": p} for p in (True, False, True, False, True)]
    _mock_runs(monkeypatch, per_run)
    report = run_detection(tmp_path, runs=5, threshold=0.8, project_root=tmp_path)
    assert report.tests == []


def test_default_threshold_includes_flaky_test(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # No threshold arg -> default -> a 3/5 flaky test appears.
    per_run = [{"t.py::test_a": p} for p in (True, False, True, False, True)]
    _mock_runs(monkeypatch, per_run)
    report = run_detection(tmp_path, runs=5, project_root=tmp_path)
    assert [t.name for t in report.tests] == ["t.py::test_a"]


def test_threshold_out_of_range_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_detection(tmp_path, runs=5, threshold=1.5, project_root=tmp_path)


def test_runs_below_one_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_detection(tmp_path, runs=0, project_root=tmp_path)


# ── ranking ─────────────────────────────────────────────────────────────────────


def test_report_ranked_by_fail_rate_descending(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # a: 1/4 pass (fail rate .75); b: 3/4 pass (fail rate .25). a ranks first.
    per_run = [
        {"t.py::a": True, "t.py::b": True},
        {"t.py::a": False, "t.py::b": True},
        {"t.py::a": False, "t.py::b": True},
        {"t.py::a": False, "t.py::b": False},
    ]
    _mock_runs(monkeypatch, per_run)
    report = run_detection(tmp_path, runs=4, project_root=tmp_path)
    assert [t.name for t in report.tests] == ["t.py::a", "t.py::b"]


# ── path containment ────────────────────────────────────────────────────────────


def test_directory_escaping_project_root_raises(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(ValueError):
        run_detection(outside, runs=3, project_root=root)


# ── serialization ────────────────────────────────────────────────────────────────


def test_write_reports_produces_both_artifacts_and_reloads(tmp_path: Path) -> None:
    report = FlakyReport(tests=[FlakyTest("t.py::a", passes=3, runs=5)], runs=5)
    json_path, md_path = write_reports(report, tmp_path, generated_at="2026-07-06T00:00:00+00:00")
    assert json_path.name == "flaky-report.json"
    assert md_path.name == "flaky-report.md"
    assert json_path.exists() and md_path.exists()
    reloaded = load_report(json_path)
    assert reloaded.runs == 5
    assert reloaded.tests[0].name == "t.py::a"
    assert reloaded.tests[0].passes == 3
    # JSON carries no timestamp -> byte-deterministic across runs.
    assert "generated" not in json_path.read_text(encoding="utf-8").lower()


def test_markdown_lists_flaky_test_pass_rate(tmp_path: Path) -> None:
    report = FlakyReport(tests=[FlakyTest("t.py::a", passes=3, runs=5)], runs=5)
    _, md_path = write_reports(report, tmp_path, generated_at="2026-07-06T00:00:00+00:00")
    text = md_path.read_text(encoding="utf-8")
    assert "3/5 passed" in text
    assert "t.py::a" in text


def test_report_json_schema_fields_present(tmp_path: Path) -> None:
    report = FlakyReport(tests=[FlakyTest("t.py::a", passes=3, runs=5)], runs=5)
    json_path, _ = write_reports(report, tmp_path, generated_at="2026-07-06T00:00:00+00:00")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(data) == {"runs", "tests"}
    assert set(data["tests"][0]) == {"name", "passes", "runs"}


# ── annotation (fail-closed) ─────────────────────────────────────────────────────


def test_annotate_labels_matching_flaky_failure(tmp_path: Path) -> None:
    report = FlakyReport(tests=[FlakyTest("tests/t.py::test_a", passes=3, runs=5)], runs=5)
    json_path, _ = write_reports(report, tmp_path, generated_at="x")
    annotated = annotate_failures(["test_a: assertion failed"], json_path)
    assert annotated == ["test_a: assertion failed — known flaky (3/5)"]


def test_annotate_leaves_nonmatching_failure_untouched(tmp_path: Path) -> None:
    report = FlakyReport(tests=[FlakyTest("tests/t.py::test_a", passes=3, runs=5)], runs=5)
    json_path, _ = write_reports(report, tmp_path, generated_at="x")
    annotated = annotate_failures(["test_other: boom"], json_path)
    assert annotated == ["test_other: boom"]


def test_annotate_does_not_match_short_name_substring_collision(tmp_path: Path) -> None:
    # Flaky `test_a` must NOT annotate a failing `test_alpha` / `test_ab` (C-01).
    report = FlakyReport(tests=[FlakyTest("tests/t.py::test_a", passes=3, runs=5)], runs=5)
    json_path, _ = write_reports(report, tmp_path, generated_at="x")
    annotated = annotate_failures(["test_alpha: boom", "test_ab: boom"], json_path)
    assert annotated == ["test_alpha: boom", "test_ab: boom"]


def test_annotate_does_not_match_full_nodeid_prefix_collision(tmp_path: Path) -> None:
    # C-01 round 2: flaky `tests/t.py::test_a` must NOT annotate a real regression
    # in `tests/t.py::test_alpha` reported in the standard `FAILED <nodeid>` format.
    report = FlakyReport(tests=[FlakyTest("tests/t.py::test_a", passes=3, runs=5)], runs=5)
    json_path, _ = write_reports(report, tmp_path, generated_at="x")
    failures = [
        "FAILED tests/t.py::test_alpha - AssertionError",
        "FAILED tests/t.py::test_ab - X",
    ]
    assert annotate_failures(failures, json_path) == failures


def test_annotate_matches_full_nodeid(tmp_path: Path) -> None:
    report = FlakyReport(tests=[FlakyTest("tests/t.py::test_a", passes=3, runs=5)], runs=5)
    json_path, _ = write_reports(report, tmp_path, generated_at="x")
    annotated = annotate_failures(["FAILED tests/t.py::test_a - AssertionError"], json_path)
    assert annotated == ["FAILED tests/t.py::test_a - AssertionError — known flaky (3/5)"]


def test_annotate_missing_report_keeps_hard_blockers(tmp_path: Path) -> None:
    annotated = annotate_failures(["test_a: boom"], tmp_path / "nope.json")
    assert annotated == ["test_a: boom"]


def test_annotate_malformed_report_keeps_hard_blockers_and_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad = tmp_path / "flaky-report.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        annotated = annotate_failures(["test_a: boom"], bad)
    assert annotated == ["test_a: boom"]
    assert any("malformed" in r.message.lower() or "unreadable" in r.message.lower() for r in caplog.records)
