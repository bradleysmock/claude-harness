"""Tests for `/build --dry-run` (ticket 0013).

Two layers:

* ``dry_run.py`` unit/integration tests — flag parsing, the ticket-mode guard,
  the "would write" plan, the spec no-persist guard, the report
  assembler/renderer, the timestamp-free gate-findings renderer, the
  self-cleaning sandboxed gate runner, and the Step 7a suppression predicate.
* Markdown content-verification tests — the flag, the new dry-run flow, and the
  Step 7a suppression note are documented in the instruction files. (Following
  the ticket-0002 precedent: markdown behaviour is verified by asserting the
  instructions exist, not by executing the model.)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from dry_run import (
    CRITIC_COVERAGE_LABEL,
    DRY_RUN_HEADER,
    GATE_COVERAGE_LABEL,
    DryRunModeError,
    assemble_dry_run_report,
    clean_stale_dry_run_tmp,
    is_ticket_mode,
    parse_dry_run_flag,
    persist_specs,
    proceed_prompt,
    render_dry_run_report,
    render_gate_findings,
    run_dry_run_gates,
    should_auto_repair,
    summarize_specs,
    validate_dry_run_mode,
    would_write_plan,
)
from models import GateError, GateResult, Spec

ROOT = Path(__file__).parent.parent


def _spec(spec_id: str = "0013-x", target: str = "dry_run.py") -> Spec:
    return Spec(
        id=spec_id,
        description="  Do the thing.  ",
        constraints=["c1"],
        acceptance_criteria=["ac1", "ac2"],
        target_file=target,
    )


# ---------------------------------------------------------------------------
# FR-1 — flag parsing + ticket-mode guard
# ---------------------------------------------------------------------------


def test_parse_detects_and_strips_flag() -> None:
    parsed = parse_dry_run_flag("--dry-run 0013")
    assert parsed.dry_run is True
    assert parsed.remainder == "0013"


def test_parse_flag_anywhere_in_args() -> None:
    parsed = parse_dry_run_flag("0013-add-inventory --dry-run")
    assert parsed.dry_run is True
    assert parsed.remainder == "0013-add-inventory"


def test_parse_absent_flag() -> None:
    parsed = parse_dry_run_flag("0013")
    assert parsed.dry_run is False
    assert parsed.remainder == "0013"


def test_parse_strips_all_occurrences() -> None:
    parsed = parse_dry_run_flag("--dry-run 0013 --dry-run")
    assert parsed.dry_run is True
    assert parsed.remainder == "0013"


def test_is_ticket_mode() -> None:
    assert is_ticket_mode("0013") is True
    assert is_ticket_mode("0013-add-inventory") is True
    assert is_ticket_mode("auth-login") is False
    assert is_ticket_mode("") is False


def test_validate_accepts_ticket_mode_dry_run() -> None:
    validate_dry_run_mode(parse_dry_run_flag("--dry-run 0013"))  # no raise


def test_validate_rejects_spec_mode_dry_run() -> None:
    with pytest.raises(DryRunModeError):
        validate_dry_run_mode(parse_dry_run_flag("--dry-run auth-login"))


def test_validate_rejects_bare_dry_run() -> None:
    with pytest.raises(DryRunModeError):
        validate_dry_run_mode(parse_dry_run_flag("--dry-run"))


def test_validate_noop_without_flag() -> None:
    validate_dry_run_mode(parse_dry_run_flag("auth-login"))  # no raise


# ---------------------------------------------------------------------------
# FR-5 — would-write plan
# ---------------------------------------------------------------------------


def test_would_write_plan_one_line_per_spec() -> None:
    specs = [_spec("a", "src/a.py"), _spec("b", "src/b.py")]
    assert would_write_plan(specs) == [
        "would write: src/a.py",
        "would write: src/b.py",
    ]


def test_would_write_plan_skips_empty_target() -> None:
    specs = [_spec("a", "src/a.py"), _spec("b", "")]
    assert would_write_plan(specs) == ["would write: src/a.py"]


# ---------------------------------------------------------------------------
# FR-6 / FR-10 — spec persistence guard
# ---------------------------------------------------------------------------


def test_persist_specs_dry_run_writes_nothing(tmp_path: Path) -> None:
    written = persist_specs([("0013-x", "spec = 1")], str(tmp_path), dry_run=True)
    assert written == []
    assert not (tmp_path / ".harness" / "specs").exists()


def test_persist_specs_live_writes_files(tmp_path: Path) -> None:
    written = persist_specs([("0013-x", "spec = 1")], str(tmp_path), dry_run=False)
    assert written == [tmp_path / ".harness" / "specs" / "0013-x.py"]
    assert written[0].read_text(encoding="utf-8") == "spec = 1"


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------


def test_summarize_specs_strips_and_copies() -> None:
    (summary,) = summarize_specs([_spec("a", "src/a.py")])
    assert summary.spec_id == "a"
    assert summary.target_file == "src/a.py"
    assert summary.description == "Do the thing."
    assert summary.acceptance_criteria == ["ac1", "ac2"]


def test_assemble_collects_all_sections() -> None:
    report = assemble_dry_run_report(
        "0013",
        [_spec("a", "src/a.py")],
        gate_findings="  gate stuff  ",
        critic_findings="  critic stuff  ",
    )
    assert report.ticket_id == "0013"
    assert report.would_write == ["would write: src/a.py"]
    assert [s.spec_id for s in report.spec_summaries] == ["a"]
    assert report.gate_findings == "gate stuff"
    assert report.critic_findings == "critic stuff"


# ---------------------------------------------------------------------------
# FR-9 / FR-11 — renderer
# ---------------------------------------------------------------------------


def _render_sample() -> str:
    report = assemble_dry_run_report(
        "0013", [_spec("a", "src/a.py")], "gate stuff", "critic stuff"
    )
    return render_dry_run_report(report)


def test_render_contains_dry_run_header() -> None:
    assert DRY_RUN_HEADER in _render_sample()


def test_render_contains_coverage_labels() -> None:
    out = _render_sample()
    assert GATE_COVERAGE_LABEL in out
    assert CRITIC_COVERAGE_LABEL in out


def test_render_contains_would_write_lines() -> None:
    assert "would write: src/a.py" in _render_sample()


def test_render_ends_with_proceed_prompt() -> None:
    out = _render_sample()
    assert out.rstrip().endswith(proceed_prompt("0013"))


def test_render_is_deterministic() -> None:
    assert _render_sample() == _render_sample()


def test_render_has_no_timestamp() -> None:
    # NFR-2: no run-varying content such as an ISO date/time.
    assert not re.search(r"\d{4}-\d{2}-\d{2}", _render_sample())


# ---------------------------------------------------------------------------
# FR-3 — gate-findings renderer
# ---------------------------------------------------------------------------


def _results() -> list[GateResult]:
    return [
        GateResult(gate="lint", passed=True, errors=[], duration_ms=12),
        GateResult(
            gate="type_check",
            passed=False,
            errors=[
                GateError(
                    message="bad type",
                    file="dry_run.py",
                    line=7,
                    column=1,
                    code="attr-defined",
                    severity="error",
                )
            ],
            duration_ms=34,
        ),
    ]


def test_render_gate_findings_reports_status_and_errors() -> None:
    out = render_gate_findings(_results(), "0013-build-dry-run-mode", "python")
    assert "# Gate Findings — 0013-build-dry-run-mode" in out
    assert "**Status**: PASS" in out
    assert "**Status**: FAIL" in out
    assert "`dry_run.py:7` [`attr-defined`]: bad type" in out
    assert "clean" in out


def test_render_gate_findings_is_deterministic_and_untimed() -> None:
    a = render_gate_findings(_results(), "slug", "python")
    b = render_gate_findings(_results(), "slug", "python")
    assert a == b
    assert not re.search(r"\d{4}-\d{2}-\d{2}", a)


def test_render_gate_findings_ignores_varying_duration() -> None:
    # NFR-2: wall-clock duration must not leak into the rendered output, so two
    # runs that differ only in gate timing render byte-identically.
    fast = [GateResult(gate="lint", passed=True, errors=[], duration_ms=3)]
    slow = [GateResult(gate="lint", passed=True, errors=[], duration_ms=9999)]
    assert render_gate_findings(fast, "slug", "python") == render_gate_findings(
        slow, "slug", "python"
    )


# ---------------------------------------------------------------------------
# FR-2 / FR-3 / FR-6 — sandboxed gate runner
# ---------------------------------------------------------------------------


def test_run_dry_run_gates_creates_and_cleans_sandbox(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def fake_runner(directory: str, language: str) -> list[GateResult]:
        seen["dir"] = directory
        # The sandbox exists while the gate runs...
        assert Path(directory).is_dir()
        # ...and the implementation is written index-prefixed (de-collision).
        assert (Path(directory) / "0_dry_run.py").exists()
        return [GateResult(gate="lint", passed=True, errors=[], duration_ms=1)]

    out = run_dry_run_gates(
        [(_spec("a", "dry_run.py"), "x = 1", "def test_x(): pass")],
        str(tmp_path),
        "python",
        gate_runner=fake_runner,
    )
    assert "**Status**: PASS" in out
    # ...and is gone afterwards (FR-6: nothing persists).
    assert not Path(seen["dir"]).exists()
    # The temp root itself has no leftover sandboxes.
    tmp_root = tmp_path / ".harness" / "dry-run-tmp"
    assert list(tmp_root.iterdir()) == []


def test_run_dry_run_gates_cleans_up_on_error(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def boom(directory: str, language: str) -> list[GateResult]:
        seen["dir"] = directory
        raise RuntimeError("gate blew up")

    with pytest.raises(RuntimeError):
        run_dry_run_gates(
            [(_spec("a", "dry_run.py"), "x = 1", "def test_x(): pass")],
            str(tmp_path),
            "python",
            gate_runner=boom,
        )
    assert not Path(seen["dir"]).exists()


def test_run_dry_run_gates_writes_nothing_to_project(tmp_path: Path) -> None:
    def ok(directory: str, language: str) -> list[GateResult]:
        return [GateResult(gate="lint", passed=True, errors=[], duration_ms=1)]

    run_dry_run_gates(
        [(_spec("a", "dry_run.py"), "x = 1", "t")],
        str(tmp_path),
        "python",
        gate_runner=ok,
    )
    # Only the (empty) temp root was created — no source files leaked out.
    leaked = [p for p in tmp_path.rglob("*.py")]
    assert leaked == []


def test_clean_stale_dry_run_tmp_removes_dir(tmp_path: Path) -> None:
    stale = tmp_path / ".harness" / "dry-run-tmp" / "old"
    stale.mkdir(parents=True)
    (stale / "leftover.py").write_text("x = 1", encoding="utf-8")
    clean_stale_dry_run_tmp(str(tmp_path))
    assert not (tmp_path / ".harness" / "dry-run-tmp").exists()


def test_clean_stale_dry_run_tmp_noop_when_absent(tmp_path: Path) -> None:
    clean_stale_dry_run_tmp(str(tmp_path))  # no raise when nothing to clean


# ---------------------------------------------------------------------------
# Step 7a suppression
# ---------------------------------------------------------------------------


def test_should_auto_repair_suppressed_in_dry_run() -> None:
    assert should_auto_repair(dry_run=True) is False
    assert should_auto_repair(dry_run=False) is True


# ---------------------------------------------------------------------------
# Markdown content-verification (the flow documents the behaviour)
# ---------------------------------------------------------------------------


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_build_command_documents_dry_run_flag() -> None:
    assert "--dry-run" in _read("commands/build.md")


def test_dry_run_flow_file_exists_and_labels_output() -> None:
    flow = _read("context/flows/build-dry-run-ticket.md")
    assert DRY_RUN_HEADER in flow
    # The flow must promise no worktree and no status transition (FR-7, FR-8).
    assert "no worktree" in flow.lower()
    assert "status.md" in flow


def test_build_ticket_flow_documents_step7a_suppression() -> None:
    flow = _read("context/flows/build-ticket.md")
    assert "DRY_RUN" in flow
    assert "should_auto_repair" in flow or "dry-run" in flow.lower()


def test_write_spec_flow_documents_dry_run_param() -> None:
    assert "dry_run" in _read("context/flows/write-spec-ticket.md")
