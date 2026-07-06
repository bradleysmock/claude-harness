"""Unit + integration tests for the /health dashboard (health.py).

Covers the computation functions with fixture data (gate pass rates, trend
boundaries, AVG(MAX(attempt)) repair cycles, error-code clustering, top failing
tickets, defensive parsing) plus a full integration run of
``format_report(health_report(root))`` over a synthesized .tickets/ tree and a
memory.db built with the real failure_records schema.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import health

# The 8-column failure_records schema mirrors memory.py (id, spec_id, gate,
# errors_text, tokens_json, outcome, attempt, timestamp).
_SCHEMA = """
CREATE TABLE failure_records (
    id          TEXT PRIMARY KEY,
    spec_id     TEXT NOT NULL,
    gate        TEXT NOT NULL,
    errors_text TEXT NOT NULL,
    tokens_json TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    attempt     INTEGER NOT NULL,
    timestamp   TEXT NOT NULL
);
"""


def _make_memory_db(path: Path, rows: list[tuple[str, str, str, str, int]]) -> None:
    """Create a memory.db at ``path`` with ``rows`` of (spec_id, gate, errors_text,
    outcome, attempt). Distinct ids so no INSERT collapses rows."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT INTO failure_records VALUES (?,?,?,?,?,?,?,?)",
            [
                (str(i), spec, gate, errors, "[]", outcome, attempt, "2026-01-01T00:00:00+00:00")
                for i, (spec, gate, errors, outcome, attempt) in enumerate(rows)
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _write_findings(root: Path, ticket: str, gates: dict[str, bool], date: str = "2026-06-01") -> Path:
    """Write a gate-findings.md under ``root/.tickets/<ticket>/`` and return its path."""
    d = root / ".tickets" / ticket
    d.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| {g:<10} | {'✓' if ok else '✗'} | |" for g, ok in gates.items())
    (d / "gate-findings.md").write_text(
        f"# Gate Findings — {ticket}\n\n## Run date: {date}\n\n### Results\n\n"
        f"| Gate | Passed | Notes |\n|------|--------|-------|\n{rows}\n",
        encoding="utf-8",
    )
    return d / "gate-findings.md"


def _pf(ticket: str, gates: dict[str, bool], mtime: float = 0.0) -> health.ParsedFindings:
    return health.ParsedFindings(ticket=ticket, date="2026-06-01", gates=gates, mtime=mtime)


# ── FR-11 / C-01: project_root validation ────────────────────────────────────


def test_health_report_rejects_nonexistent_dir():
    # FR-11: a non-existent project_root raises ValueError before any FS access.
    # (solution.md names "/etc" for C-01, but /etc is a real directory on POSIX;
    # the actual contract is "not an existing directory", tested here honestly.)
    with pytest.raises(ValueError):
        health.health_report("/no/such/dir/xyzzy-12345")


def test_health_report_rejects_file_path(tmp_path):
    # FR-11: a path to a regular file (not a directory) also raises ValueError.
    f = tmp_path / "a_file"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        health.health_report(str(f))


# ── FR-6: trend indicator boundaries ─────────────────────────────────────────


@pytest.mark.parametrize(
    "last,prior,expected",
    [
        (0.60, 0.50, "stable"),     # delta == 0.10 exactly -> stable
        (0.61, 0.50, "improving"),  # delta ~0.11 -> improving
        (0.50, 0.61, "declining"),  # delta ~-0.11 -> declining
        (0.50, 0.50, "stable"),     # equal rates -> stable
        (1.00, 0.00, "improving"),
    ],
)
def test_trend_indicator_boundaries(last, prior, expected):
    assert health.trend_indicator(last, prior) == expected


# ── FR-2: pass rate by gate ──────────────────────────────────────────────────


def test_pass_rate_by_gate_counts_and_denominator():
    builds = [
        _pf("t1", {"lint": True, "test": True}, mtime=3),
        _pf("t2", {"lint": False, "test": True}, mtime=2),
        _pf("t3", {"lint": True}, mtime=1),
    ]
    by_gate = {pr.gate: pr for pr in health.pass_rate_by_gate(builds)}
    assert by_gate["lint"].passed == 2
    assert by_gate["lint"].total == 3
    assert by_gate["test"].passed == 2
    assert by_gate["test"].total == 2


def test_pass_rate_annotation_in_output():
    # FR-7: the pass-rate section carries an "N of M builds analyzed" annotation.
    report = health.HealthReport(
        pass_rates=[health.GatePassRate("lint", 2, 3, "stable")],
        builds_analyzed=3,
        builds_window=10,
        top_failing_tickets=[],
        memory_db_present=False,
        avg_repair_cycles=None,
        top_failure_modes=None,
        notes=[],
    )
    out = health.format_report(report)
    assert "3 of 10 builds analyzed" in out
    assert "Gate" in out and "Pass Rate" in out and "Trend" in out


# ── FR-3: average repair cycles = AVG(MAX(attempt)) per (spec, gate) ──────────


def test_avg_repair_cycles_uses_max_attempt_per_spec(tmp_path):
    db = tmp_path / "memory.db"
    # specA/lint passed at attempts 1 and 3 -> per-spec MAX = 3.
    # specB/lint passed at attempt 1        -> per-spec MAX = 1.
    # AVG(MAX) per gate = (3 + 1) / 2 = 2.0. A naive AVG(attempt) over passed rows
    # would be (1 + 3 + 1) / 3 ≈ 1.667 — this asserts the two-level aggregation.
    _make_memory_db(
        db,
        [
            ("specA", "lint", "warn", "passed", 1),
            ("specA", "lint", "warn", "passed", 3),
            ("specB", "lint", "warn", "passed", 1),
        ],
    )
    cycles = health.avg_repair_cycles(db)
    assert cycles is not None
    assert cycles["lint"] == pytest.approx(2.0)


def test_avg_repair_cycles_ignores_failed_only_pairs(tmp_path):
    db = tmp_path / "memory.db"
    _make_memory_db(
        db,
        [
            ("specA", "lint", "e", "failed", 1),
            ("specA", "lint", "e", "passed", 2),
            ("specB", "test", "e", "failed", 1),  # never passed -> excluded entirely
        ],
    )
    cycles = health.avg_repair_cycles(db)
    assert cycles == {"lint": pytest.approx(2.0)}


def test_avg_repair_cycles_absent_db(tmp_path):
    assert health.avg_repair_cycles(tmp_path / "nope.db") is None


# ── FR-4: top failure modes cluster by error code ────────────────────────────


def test_top_failure_modes_lists_codes_not_raw_text(tmp_path):
    db = tmp_path / "memory.db"
    rows = []
    for i in range(10):
        rows.append((f"s{i}", "security", f"B102 exec_used at line {i}", "failed", 1))
    for i in range(5):
        rows.append((f"e{i}", "lint", f"E501 line too long ({i})", "failed", 1))
    for i in range(3):
        rows.append((f"t{i}", "type_check", f"error TS2345 bad arg {i}", "failed", 1))
    # A passed row with a code must be excluded (outcome != 'passed' filter).
    rows.append(("p", "lint", "B999 should be ignored", "passed", 1))
    # Raw text without any code must not create a bogus mode.
    rows.append(("r", "test", "assertion failed, no code here", "failed", 1))
    _make_memory_db(db, rows)

    modes = health.top_failure_modes(db)
    assert modes == [("B102", 10), ("E501", 5), ("TS2345", 3)]
    codes = {c for c, _ in modes}
    assert "B999" not in codes  # excluded (passed)


def test_top_failure_modes_absent_db(tmp_path):
    assert health.top_failure_modes(tmp_path / "nope.db") is None


# ── FR-5: top failing tickets ────────────────────────────────────────────────


def test_top_failing_tickets_sorted_by_failure_count():
    builds = [
        _pf("t1", {"lint": False, "test": False, "security": False}),  # 3 fails
        _pf("t2", {"lint": False}),                                     # 1 fail
        _pf("t3", {"lint": False, "test": False}),                      # 2 fails
        _pf("t4", {"lint": True, "test": True}),                        # 0 fails -> excluded
    ]
    ranked = health.top_failing_tickets(builds)
    assert ranked == [("t1", 3), ("t3", 2), ("t2", 1)]


# ── FR-9: defensive parsing of malformed gate-findings.md ────────────────────


def test_malformed_gate_findings_skipped_with_warning(tmp_path, capsys):
    _write_findings(tmp_path, "0001-good", {"lint": True, "test": False})
    bad = tmp_path / ".tickets" / "0002-bad"
    bad.mkdir(parents=True)
    (bad / "gate-findings.md").write_text("# Not a real findings file\n\nno table here\n", encoding="utf-8")

    report = health.health_report(str(tmp_path))  # must not raise
    assert report.builds_analyzed == 1  # only the good file parsed (N reflects skip)
    assert any("skipped" in n for n in report.notes)
    assert "malformed" in capsys.readouterr().err


def test_parse_gate_findings_returns_none_on_malformed(tmp_path):
    p = tmp_path / "gate-findings.md"
    p.write_text("# nothing structured\n", encoding="utf-8")
    assert health.parse_gate_findings(p) is None


def test_parse_gate_findings_reads_table(tmp_path):
    p = _write_findings(tmp_path, "0007-x", {"lint": True, "type_check": False, "test": True})
    parsed = health.parse_gate_findings(p)
    assert parsed is not None
    assert parsed.ticket == "0007-x"
    assert parsed.gates == {"lint": True, "type_check": False, "test": True}


# ── FR-10: absent memory.db handled gracefully ───────────────────────────────


def test_absent_memory_db_omits_sections_with_note(tmp_path):
    _write_findings(tmp_path, "0001-x", {"lint": True})
    report = health.health_report(str(tmp_path))
    assert report.memory_db_present is False
    assert report.avg_repair_cycles is None
    assert report.top_failure_modes is None
    assert any("memory.db" in n for n in report.notes)


# ── FR-8: discovery is mtime-sorted and capped at the window ──────────────────


def test_discovery_capped_to_window(tmp_path):
    for i in range(health.WINDOW + 5):
        _write_findings(tmp_path, f"{i:04d}-t", {"lint": i % 2 == 0})
    found = health.discover_gate_findings(tmp_path)
    assert len(found) == health.WINDOW


# ── FR-1–FR-8: full integration ──────────────────────────────────────────────


def test_integration_full_report(tmp_path, capsys):
    _write_findings(tmp_path, "0001-alpha", {"lint": True, "type_check": True, "test": True})
    _write_findings(tmp_path, "0002-beta", {"lint": False, "type_check": True, "test": False})
    _write_findings(tmp_path, "0003-gamma", {"lint": True, "type_check": False, "test": True})

    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    _make_memory_db(
        harness_dir / "memory.db",
        [
            ("specA", "lint", "E501 too long", "failed", 1),
            ("specA", "lint", "E501 too long again", "passed", 2),
            ("specB", "security", "B102 exec_used", "failed", 1),
            ("specB", "security", "B102 exec_used fixed", "passed", 2),
        ],
    )

    out = health.format_report(health.health_report(str(tmp_path)))

    # Section headers present.
    for header in (
        "Harness Health Dashboard",
        "Gate Pass Rates",
        "Average Repair Cycles",
        "Top Recurring Failure Modes",
        "Tickets With Most Gate Failures",
    ):
        assert header in out
    # Column names + N-of-M annotation.
    assert "Pass Rate" in out and "Trend" in out
    assert "3 of 10 builds analyzed" in out
    # Data surfaced from memory.db.
    assert "E501" in out or "B102" in out
    assert "lint" in out


def test_main_exit_codes(tmp_path, capsys):
    # Invalid project_root -> non-zero exit.
    assert health.main(["/no/such/dir/xyzzy-12345"]) == 2
    # Existing dir without .tickets/ -> non-zero exit.
    assert health.main([str(tmp_path)]) == 2
    # Valid harness tree -> exit 0 and prints the dashboard.
    _write_findings(tmp_path, "0001-x", {"lint": True})
    assert health.main([str(tmp_path)]) == 0
    assert "Harness Health Dashboard" in capsys.readouterr().out
