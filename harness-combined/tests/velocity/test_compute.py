"""Unit + integration tests for skills/velocity/compute.py.

Fixtures are materialized in a pytest ``tmp_path`` tree so no ``.tickets`` dot
directory is committed. The integration tests scan that tree with
``scan_completed`` and drive the arithmetic through the real stdin CLI.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_COMPUTE_PATH = Path(__file__).resolve().parents[2] / "skills" / "velocity" / "compute.py"

_spec = importlib.util.spec_from_file_location("velocity_compute", _COMPUTE_PATH)
assert _spec and _spec.loader
compute_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compute_mod)


# ── fixture tree builder ──────────────────────────────────────────────────────


def _write_ticket(completed: Path, name: str, *, start: str | None, end: str | None,
                  title: str = "Fixture") -> None:
    ticket = completed / name
    ticket.mkdir(parents=True)
    date_line = f"**Date**: {start}\n" if start is not None else "no date here\n"
    (ticket / "problem.md").write_text(f"# Problem\n{date_line}")
    updated_line = f"updated: {end}\n" if end is not None else "updated: not-a-date\n"
    (ticket / "status.md").write_text(f"status: done\ntitle: {title}\n{updated_line}")


def _build_fixture(root: Path) -> Path:
    completed = root / ".tickets" / "completed"
    completed.mkdir(parents=True)
    _write_ticket(completed, "9001-alpha", start="2026-01-01", end="2026-01-11", title="Alpha")
    _write_ticket(completed, "9002-beta", start="2026-01-05", end="2026-01-08", title="Beta")
    _write_ticket(completed, "9003-gamma", start="2026-01-19", end="2026-01-19", title="Gamma")
    _write_ticket(completed, "9004-delta", start=None, end="2026-01-20", title="Delta")
    _write_ticket(completed, "9005-epsilon", start="2026-01-30", end="2026-01-10", title="Epsilon")
    return root


def _run_cli(payload: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_COMPUTE_PATH)],
        input=payload,
        capture_output=True,
        text=True,
    )


# ── FR-4: cycle-time determinism ──────────────────────────────────────────────


def test_cycle_days_ten():
    assert compute_mod.cycle_days("2026-01-01", "2026-01-11") == 10


def test_cycle_days_zero_same_day():
    assert compute_mod.cycle_days("2026-01-19", "2026-01-19") == 0


def test_compute_is_deterministic():
    payload = json.dumps([{"id": "A", "start": "2026-01-01", "end": "2026-01-11"}])
    first = _run_cli(payload)
    second = _run_cli(payload)
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["tickets"][0]["days"] == 10
    assert result["overall_avg"] == 10.0


# ── FR-5: ISO week grouping incl. year boundary ───────────────────────────────


def test_iso_week_year_boundary_2020():
    assert compute_mod.iso_week("2021-01-01") == (2020, 53)


def test_iso_week_year_boundary_2021():
    assert compute_mod.iso_week("2021-01-04") == (2021, 1)


def test_weekly_grouping_splits_across_weeks():
    entries = [
        {"id": "a", "start": "2021-01-01", "end": "2021-01-01"},  # (2020, 53)
        {"id": "b", "start": "2021-01-04", "end": "2021-01-04"},  # (2021, 1)
    ]
    weekly = compute_mod.compute(entries)["weekly"]
    keys = {(row["iso_year"], row["iso_week"]) for row in weekly}
    assert keys == {(2020, 53), (2021, 1)}


# ── FR-9 / FR-10: skip-and-report ─────────────────────────────────────────────


def test_negative_cycle_time_skipped():
    result = compute_mod.compute([{"id": "x", "start": "2026-01-30", "end": "2026-01-10"}])
    assert result["tickets"] == []
    assert result["skipped"] == 1


def test_malformed_date_entry_skipped_not_fatal():
    result = compute_mod.compute(
        [
            {"id": "ok", "start": "2026-01-01", "end": "2026-01-05"},
            {"id": "bad", "start": "2026/01/01", "end": "2026-01-05"},
        ]
    )
    assert result["skipped"] == 1
    assert [t["id"] for t in result["tickets"]] == ["ok"]


def test_malformed_json_exits_1_no_traceback():
    proc = _run_cli("this is not json")
    assert proc.returncode == 1
    assert proc.stdout == ""  # no partial JSON, no traceback on stdout
    err = json.loads(proc.stderr)
    assert err["error"] == "invalid JSON input"
    assert "Traceback" not in proc.stderr


def test_non_array_input_exits_1():
    proc = _run_cli(json.dumps({"not": "an array"}))
    assert proc.returncode == 1
    assert proc.stdout == ""


# ── extraction regexes ────────────────────────────────────────────────────────


def test_extract_start_present_and_absent():
    assert compute_mod.extract_start("**Date**: 2026-06-21") == "2026-06-21"
    assert compute_mod.extract_start("Date is 2026-06-21") is None  # wrong marker
    assert compute_mod.extract_start("**Date**: 21-06-2026") is None  # wrong format


def test_extract_end_returns_latest():
    text = "updated: 2026-01-01\nsome text\nupdated: 2026-02-02\n"
    assert compute_mod.extract_end(text) == "2026-02-02"
    assert compute_mod.extract_end("no date") is None


def test_extract_title():
    assert compute_mod.extract_title("title: Ticket velocity report\n") == "Ticket velocity report"
    assert compute_mod.extract_title("no title") is None


# ── FR-11 / Security: path containment ────────────────────────────────────────


def test_is_contained_accepts_descendant(tmp_path):
    root = tmp_path / "harness"
    (root / "sub").mkdir(parents=True)
    assert compute_mod.is_contained(root / "sub", root) is True
    assert compute_mod.is_contained(root, root) is True


def test_is_contained_rejects_escape(tmp_path):
    root = tmp_path / "harness"
    root.mkdir()
    escape = root / ".." / ".." / "etc"
    assert compute_mod.is_contained(escape, root) is False


def test_scan_skips_symlinked_ticket_escaping_root(tmp_path):
    """FR-11 integration: a ticket dir under completed/ that is a symlink whose
    .resolve() lands outside the harness root is skipped, not read through.

    This exercises the real skip branch in scan_completed (the direct
    is_contained test cannot, since glob('*') never yields a traversal string).
    """
    root = tmp_path / "harness"
    completed = root / ".tickets" / "completed"
    completed.mkdir(parents=True)
    # A well-formed ticket that lives OUTSIDE the harness root.
    outside = tmp_path / "outside_ticket"
    _write_ticket(tmp_path, "outside_ticket", start="2026-01-01", end="2026-01-11", title="Evil")
    # completed/9099-evil -> ../../outside_ticket (escapes root on resolve()).
    link = completed / "9099-evil"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform without symlink perms
        import pytest

        pytest.skip("symlinks not supported on this platform")
    entries, skipped = compute_mod.scan_completed(root)
    assert all(e["id"] != "9099" for e in entries), "escaping symlink must not be scanned in"
    assert ("9099-evil", "path escapes harness root") in skipped


# ── FR-1 / FR-6 / FR-7: integration over a fixture tree ───────────────────────


def test_scan_discovers_valid_and_skips_bad(tmp_path):
    root = _build_fixture(tmp_path)
    entries, skipped = compute_mod.scan_completed(root)
    ids = sorted(e["id"] for e in entries)
    # scan skips only missing/malformed date FIELDS (9004); 9005 has both dates
    # present, so its negative range is caught downstream by compute().
    assert ids == ["9001", "9002", "9003", "9005"]
    skipped_names = sorted(name for name, _ in skipped)
    assert skipped_names == ["9004-delta"]


def test_integration_pipeline_end_to_end(tmp_path):
    root = _build_fixture(tmp_path)
    entries, scan_skipped = compute_mod.scan_completed(root)
    payload = json.dumps([{k: e[k] for k in ("id", "start", "end")} for e in entries])
    proc = _run_cli(payload)
    assert proc.returncode == 0
    result = json.loads(proc.stdout)
    assert len(result["tickets"]) == 3
    # (10 + 3 + 0) / 3 == 4.33 — matches manual sum/count from the detail table.
    assert result["overall_avg"] == 4.33
    days_by_id = {t["id"]: t["days"] for t in result["tickets"]}
    assert days_by_id == {"9001": 10, "9002": 3, "9003": 0}
    # Combined skip accounting the skill surfaces: 9004 (missing date, scan) +
    # 9005 (negative range, compute) == 2.
    assert len(scan_skipped) + result["skipped"] == 2


def test_scan_title_extracted(tmp_path):
    root = _build_fixture(tmp_path)
    entries, _ = compute_mod.scan_completed(root)
    titles = {e["id"]: e["title"] for e in entries}
    assert titles["9001"] == "Alpha"


# ── FR-8: empty completed dir ─────────────────────────────────────────────────


def test_scan_empty_completed_dir(tmp_path):
    (tmp_path / ".tickets" / "completed").mkdir(parents=True)
    entries, skipped = compute_mod.scan_completed(tmp_path)
    assert entries == []
    assert skipped == []


def test_compute_empty_no_zero_division():
    result = compute_mod.compute([])
    assert result["tickets"] == []
    assert result["weekly"] == []
    assert result["overall_avg"] == 0.0
    assert result["skipped"] == 0


# ── min/max in weekly rows, zero-day safe ─────────────────────────────────────


def test_weekly_min_max_and_zero_day():
    # Three same-ISO-week completion dates: 2026-01-19 (0d), plus two more in W4.
    entries = [
        {"id": "z", "start": "2026-01-19", "end": "2026-01-19"},  # 0 days
        {"id": "a", "start": "2026-01-14", "end": "2026-01-19"},  # 5 days
    ]
    weekly = compute_mod.compute(entries)["weekly"]
    assert len(weekly) == 1
    row = weekly[0]
    assert row["min_days"] == 0
    assert row["max_days"] == 5
    assert row["count"] == 2


def test_sanity_isocalendar_matches_stdlib():
    # Guard against a regressed iso_week helper.
    assert compute_mod.iso_week(date(2026, 1, 11)) == date(2026, 1, 11).isocalendar()[:2]
