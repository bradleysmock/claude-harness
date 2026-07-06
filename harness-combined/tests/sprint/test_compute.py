"""Unit + integration tests for skills/sprint/compute.py.

The module is loaded by path (it lives under ``skills/`` which is not an
importable package) and the CLI is driven over a real subprocess + stdin, the
same way ``tests/velocity/test_compute.py`` exercises the velocity helper.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

_COMPUTE_PATH = Path(__file__).resolve().parents[2] / "skills" / "sprint" / "compute.py"

_spec = importlib.util.spec_from_file_location("sprint_compute", _COMPUTE_PATH)
assert _spec and _spec.loader
compute = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compute)

AS_OF = date(2026, 6, 21)  # a Sunday — Sprint 1 Monday is 2026-06-22


def _ticket(number, *, title=None, effort="medium", depends_on=None,
            status="solution", completed=False):
    return {
        "number": number,
        "title": title or f"Ticket {number}",
        "effort": effort,
        "status": status,
        "depends_on": depends_on or [],
        "completed": completed,
    }


def _plan(tickets, **kw):
    kw.setdefault("as_of", AS_OF)
    return compute.plan(tickets, **kw)


def _sprint_of(result, number):
    """Return the 1-based sprint ``n`` a ticket landed in, or None."""
    for sprint in result["sprints"]:
        if any(t["number"] == number for t in sprint["tickets"]):
            return sprint["n"]
    return None


# ── FR-2: effort mapping ──────────────────────────────────────────────────────

def test_effort_mapping_small_medium_large():
    assert compute.effort_points("small") == (1, False)
    assert compute.effort_points("medium") == (2, False)
    assert compute.effort_points("large") == (3, False)


def test_effort_missing_defaults_to_medium_with_flag():
    assert compute.effort_points(None) == (2, True)
    assert compute.effort_points("") == (2, True)
    assert compute.effort_points("gigantic") == (2, True)


def test_missing_effort_emits_visible_warning():
    result = _plan([_ticket("0001", effort=None)])
    assert any("0001" in w and "medium" in w for w in result["warnings"])
    # ticket is still planned at 2 points
    sprint = result["sprints"][0]
    assert sprint["tickets"][0]["effort_pts"] == 2


# ── FR-3: capacity flag ───────────────────────────────────────────────────────

def test_capacity_flag_changes_assignments():
    tickets = [_ticket(n, effort="large") for n in ("0001", "0002", "0003")]
    cap6 = _plan(tickets, capacity=6)   # 3+3 -> sprint1 (6), 3 -> sprint2
    cap4 = _plan(tickets, capacity=4)   # 3 per sprint -> three sprints
    assert _sprint_of(cap6, "0002") == 1
    assert _sprint_of(cap4, "0002") == 2
    assert _sprint_of(cap6, "0003") == 2
    assert _sprint_of(cap4, "0003") == 3


# ── FR-4: sprint labels via --as-of ───────────────────────────────────────────

def test_sprint1_monday_is_following_week():
    assert compute.sprint1_monday(date(2026, 6, 21)) == date(2026, 6, 22)


def test_sprint_label_format():
    result = _plan([_ticket("0001")])
    assert result["sprints"][0]["label"] == "Sprint 1 — Week of 2026-06-22"


def test_sprint_labels_advance_one_week():
    # two large tickets at capacity 3 -> two sprints, labels one week apart
    tickets = [_ticket("0001", effort="large"), _ticket("0002", effort="large")]
    result = _plan(tickets, capacity=3)
    labels = {s["n"]: s["label"] for s in result["sprints"]}
    assert labels[1] == "Sprint 1 — Week of 2026-06-22"
    assert labels[2] == "Sprint 2 — Week of 2026-06-29"


# ── FR-5: dependency ordering ─────────────────────────────────────────────────

def test_dependency_placed_in_later_sprint():
    tickets = [_ticket("0001"), _ticket("0002", depends_on=["0001"])]
    result = _plan(tickets)
    assert _sprint_of(result, "0002") > _sprint_of(result, "0001")


def test_dependency_with_reduced_capacity():
    # Both large (3pts), capacity 4: A fills sprint1 (3/4), B (3pts) cannot fit
    # the 1 remaining point AND must be strictly after A -> sprint 2+.
    tickets = [_ticket("0001", effort="large"),
               _ticket("0002", effort="large", depends_on=["0001"])]
    result = _plan(tickets, capacity=4)
    assert _sprint_of(result, "0001") == 1
    assert _sprint_of(result, "0002") >= 2


# ── FR-1: completed tickets are pre-satisfied dependencies ────────────────────

def test_dependency_on_completed_ticket_not_blocked():
    tickets = [
        _ticket("0001", completed=True),
        _ticket("0002", depends_on=["0001"]),
    ]
    result = _plan(tickets)
    assert _sprint_of(result, "0002") == 1  # unblocked -> earliest sprint
    assert result["overflow"] == []
    assert not any("0001" in w for w in result["warnings"])


# ── FR-6: cycle detection ─────────────────────────────────────────────────────

def test_cycle_raises_cycle_error_with_members():
    tickets = [_ticket("0001", depends_on=["0002"]),
               _ticket("0002", depends_on=["0001"])]
    try:
        _plan(tickets)
        assert False, "expected CycleError"
    except compute.CycleError as exc:
        assert set(exc.members) == {"0001", "0002"}


def test_cycle_cli_exits_nonzero_naming_members():
    tickets = [_ticket("0001", depends_on=["0002"]),
               _ticket("0002", depends_on=["0001"])]
    proc = _run_cli(tickets, ["--as-of", "2026-06-21"])
    assert proc.returncode == 1
    assert proc.stdout == ""  # no partial plan
    assert "0001" in proc.stderr and "0002" in proc.stderr


# ── FR-7: output structure ────────────────────────────────────────────────────

def test_output_has_sprint_ticket_and_capacity_fields():
    result = _plan([_ticket("0001", title="Alpha", effort="small")])
    sprint = result["sprints"][0]
    assert sprint["capacity_total"] == 6
    assert sprint["capacity_used"] == 1
    t = sprint["tickets"][0]
    assert t["number"] == "0001"
    assert t["title"] == "Alpha"
    assert t["effort"] == "small"
    assert t["status"] == "solution"


# ── FR-8: overflow beyond max sprints ─────────────────────────────────────────

def test_overflow_beyond_max_sprints():
    # three large tickets, capacity 3 -> one per sprint, but max 2 sprints
    tickets = [_ticket(n, effort="large") for n in ("0001", "0002", "0003")]
    result = _plan(tickets, capacity=3, max_sprints=2)
    assert len(result["sprints"]) == 2
    overflow_numbers = {o["number"] for o in result["overflow"]}
    assert "0003" in overflow_numbers


def test_effort_exceeds_capacity_goes_to_overflow():
    # a large (3pt) ticket cannot fit a capacity-2 sprint under any schedule
    result = _plan([_ticket("0001", effort="large")], capacity=2)
    assert result["sprints"] == []
    assert len(result["overflow"]) == 1
    assert "exceeds sprint capacity" in result["overflow"][0]["reason"]


# ── Pack-time overflow must cascade to dependents (fail-closed FR-5) ───────────

def test_dependent_of_capacity_overflowed_ticket_is_not_scheduled():
    # A (large) can't fit capacity-2 -> overflow; B depends on A and must NOT be
    # scheduled ahead of its unplanned dependency.
    tickets = [_ticket("0001", effort="large"),
               _ticket("0002", effort="small", depends_on=["0001"])]
    result = _plan(tickets, capacity=2)
    assert _sprint_of(result, "0002") is None
    overflow_numbers = {o["number"] for o in result["overflow"]}
    assert overflow_numbers == {"0001", "0002"}
    reason = next(o["reason"] for o in result["overflow"] if o["number"] == "0002")
    assert "0001" in reason


def test_dependent_beyond_max_sprints_cascades_to_overflow():
    # A chain longer than max_sprints: the tail dependency overflows, and its
    # dependent must cascade rather than land in an early sprint.
    tickets = [_ticket("0001", effort="large")]
    prev = "0001"
    for i in range(2, 5):  # 0002..0004 chained, each large
        num = f"{i:04d}"
        tickets.append(_ticket(num, effort="large", depends_on=[prev]))
        prev = num
    result = _plan(tickets, capacity=3, max_sprints=2)
    # sprints 1 and 2 hold 0001, 0002; 0003 overflows (no sprint 3), 0004 cascades
    assert _sprint_of(result, "0003") is None
    assert _sprint_of(result, "0004") is None
    overflow_numbers = {o["number"] for o in result["overflow"]}
    assert {"0003", "0004"} <= overflow_numbers


# ── #4 title sanitization (Markdown-injection parity with depends-on) ─────────

def test_title_pipe_and_newline_sanitized():
    assert compute.sanitize_title("Add | pipe") == "Add \\| pipe"
    assert compute.sanitize_title("multi\nline\ttitle") == "multi line title"
    result = _plan([_ticket("0001", title="Break | row")])
    assert result["sprints"][0]["tickets"][0]["title"] == "Break \\| row"


# ── #5 invalid capacity/max-sprints clamp is warned, not silent ───────────────

def test_invalid_capacity_is_clamped_with_warning():
    result = _plan([_ticket("0001")], capacity=0)
    assert any("sprint-capacity" in w for w in result["warnings"])
    # falls back to default 6 -> ticket still planned
    assert _sprint_of(result, "0001") == 1


def test_invalid_max_sprints_is_clamped_with_warning():
    result = _plan([_ticket("0001")], max_sprints=0)
    assert any("max-sprints" in w for w in result["warnings"])
    assert _sprint_of(result, "0001") == 1


# ── NFR-2: compute writes no files ────────────────────────────────────────────

def test_compute_cli_writes_no_files(tmp_path):
    (tmp_path / "sentinel.txt").write_text("x")  # a file to detect mutation of
    baseline = {p: p.stat().st_mtime_ns for p in sorted(tmp_path.rglob("*"))}
    proc = subprocess.run(
        [sys.executable, str(_COMPUTE_PATH), "--as-of", "2026-06-21"],
        input=json.dumps([_ticket("0001")]),
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert proc.returncode == 0
    after = {p: p.stat().st_mtime_ns for p in sorted(tmp_path.rglob("*"))}
    assert after == baseline  # no new/removed/modified files under cwd


# ── FR-9: unresolvable dependency -> overflow + named warning ─────────────────

def test_unresolvable_dependency_goes_to_overflow():
    tickets = [_ticket("0001", depends_on=["9999"]), _ticket("0002")]
    result = _plan(tickets)
    overflow_numbers = {o["number"] for o in result["overflow"]}
    assert "0001" in overflow_numbers
    assert _sprint_of(result, "0002") == 1  # others still planned
    reason = next(o["reason"] for o in result["overflow"] if o["number"] == "0001")
    assert "9999" in reason
    assert any("0001" in w and "9999" in w for w in result["warnings"])


# ── Field validation: invalid depends-on tokens excluded + warned ─────────────

def test_invalid_depends_on_token_excluded_and_warned():
    tickets = [_ticket("0001", depends_on=["[0002](evil)"]), _ticket("0002")]
    result = _plan(tickets)
    # 0001 is planned (bad token dropped, not treated as a real dep)
    assert _sprint_of(result, "0001") is not None
    assert any("0001" in w and "invalid" in w.lower() for w in result["warnings"])


# ── Whitespace stripping in depends-on tokens ─────────────────────────────────

def test_depends_on_whitespace_is_stripped():
    assert compute.normalize_deps("0001, 0002") == ["0001", "0002"]
    assert compute.normalize_deps(" 0001 ,0002 ") == ["0001", "0002"]
    # a spaced comma string still resolves as two real deps
    tickets = [_ticket("0001"), _ticket("0002"),
               _ticket("0003", depends_on="0001, 0002")]
    result = _plan(tickets)
    assert _sprint_of(result, "0003") >= 2


# ── NFR-1: performance on a 100-ticket backlog ────────────────────────────────

def test_hundred_ticket_backlog_under_five_seconds():
    tickets = [_ticket(f"{i:04d}", effort="small") for i in range(1, 101)]
    start = time.monotonic()
    result = _plan(tickets, capacity=6, max_sprints=50)
    elapsed = time.monotonic() - start
    assert elapsed < 5.0
    planned = sum(len(s["tickets"]) for s in result["sprints"])
    assert planned + len(result["overflow"]) == 100


# ── CLI: stdin contract ───────────────────────────────────────────────────────

def _run_cli(tickets, extra_args):
    payload = json.dumps(tickets)
    return subprocess.run(
        [sys.executable, str(_COMPUTE_PATH), *extra_args],
        input=payload,
        capture_output=True,
        text=True,
    )


def test_cli_reads_stdin_and_emits_plan():
    proc = _run_cli([_ticket("0001", effort="small")], ["--as-of", "2026-06-21"])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["sprints"][0]["label"] == "Sprint 1 — Week of 2026-06-22"


def test_cli_rejects_non_array_input():
    proc = subprocess.run(
        [sys.executable, str(_COMPUTE_PATH), "--as-of", "2026-06-21"],
        input='{"not": "an array"}',
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "array" in proc.stderr.lower()


def test_cli_requires_valid_as_of():
    proc = _run_cli([_ticket("0001")], ["--as-of", "not-a-date"])
    assert proc.returncode == 1
    assert "as-of" in proc.stderr.lower()
