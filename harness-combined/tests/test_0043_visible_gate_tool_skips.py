"""Ticket 0043 — missing gate tools must be visible, never silent passes.

Covers the four functional requirements:
- FR-1: gates.tool_skipped() helper + the go/rust silent-skip sites.
- FR-2: stop_full_gate accumulates missing executables and reports them per stack
  (exit 0 when otherwise clean, joined into the blocking report when it exits 2).
- FR-3: the findings renderer emits a Skipped Tools section for TOOL_SKIPPED
  entries (and the doc documents it).
- FR-4: build-ticket.md Step 1 surfaces the skipped-tool list, citing ticket 0022.
"""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
from pathlib import Path

import gates.go as go
import gates.rust as rust
import server
from gates import tool_skipped
from models import GateError, GateResult, LanguageResult, StackName

ROOT = Path(__file__).parent.parent
HOOKS = ROOT / "hooks"


def _load_hook():
    spec = importlib.util.spec_from_file_location("stop_full_gate", HOOKS / "stop_full_gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["stop_full_gate"] = module
    spec.loader.exec_module(module)
    return module


gate = _load_hook()


def _absent(*names: str):
    """A shutil.which stand-in where the named tools are missing, others present."""
    absent = set(names)
    return lambda name: None if name in absent else f"/usr/bin/{name}"


# ── FR-1: the shared helper ─────────────────────────────────────────────────

def test_tool_skipped_is_a_passing_warning() -> None:
    r = tool_skipped("staticcheck", "staticcheck", "go install honnef.co/go/tools/cmd/staticcheck@latest")
    assert r.passed is True
    assert r.duration_ms == 0
    assert len(r.errors) == 1
    e = r.errors[0]
    assert e.code == "TOOL_SKIPPED"
    assert e.severity == "warning"
    assert "staticcheck" in e.message
    assert "go install" in e.message  # the install hint is present


def test_tool_skipped_is_distinct_from_tool_error() -> None:
    # TOOL_SKIPPED (passing warning) must never be confused with TOOL_ERROR
    # (failing error — tool present but crashed). NFR-1.
    r = tool_skipped("audit", "cargo-audit", "cargo install cargo-audit")
    assert r.errors[0].code == "TOOL_SKIPPED"
    assert r.errors[0].code != "TOOL_ERROR"
    assert r.passed is True


# ── FR-1: the two silent-skip gate sites ────────────────────────────────────

def test_go_staticcheck_absent_yields_tool_skipped(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", _absent("staticcheck"))
    r = go._staticcheck_gate("/tmp")
    assert r.passed is True  # no change to pass/fail semantics (NFR-2)
    assert [e.code for e in r.errors] == ["TOOL_SKIPPED"]
    assert "staticcheck" in r.errors[0].message


def test_rust_cargo_audit_absent_yields_tool_skipped(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", _absent("cargo-audit"))
    r = rust._audit_gate("/tmp")
    assert r.passed is True
    assert [e.code for e in r.errors] == ["TOOL_SKIPPED"]
    assert "cargo-audit" in r.errors[0].message


# ── FR-2: the Stop hook accumulates missing executables ─────────────────────

def test_run_gate_records_missing_executable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gate.shutil, "which", _absent("phantom-tool"))
    skipped: list[str] = []
    code, out = gate.run_gate("phantom-tool", ["--version"], tmp_path, skipped=skipped)
    assert code is None  # non-run sentinel, distinct from 0 (ran clean)
    assert out == ""
    assert skipped == ["phantom-tool"]


def test_run_gate_dedupes_missing_executable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gate.shutil, "which", _absent("phantom-tool"))
    skipped: list[str] = []
    gate.run_gate("phantom-tool", [], tmp_path, skipped=skipped)
    gate.run_gate("phantom-tool", [], tmp_path, skipped=skipped)
    assert skipped == ["phantom-tool"]


def test_gates_python_reports_absent_pytest(tmp_path: Path, monkeypatch) -> None:
    # pytest absent, no git repo -> no py files -> only pytest is attempted.
    monkeypatch.setattr(gate.shutil, "which", _absent("pytest"))
    report = gate.gates_python(tmp_path)
    assert report.failures == []
    assert "pytest" in report.skipped


def test_main_skip_only_exits_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    ctx = gate.TicketContext(ticket_dir=tmp_path, worktree_dir=tmp_path / "0043-wt")
    monkeypatch.setattr(gate, "discover_tickets_to_gate", lambda _root: [ctx])
    monkeypatch.setattr(
        gate, "collect_report",
        lambda _wt, stacks=None: ([], ["python: skipped (not installed) — pytest"]),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    rc = gate.main()
    err = capsys.readouterr().err
    assert rc == 0  # skips alone never block
    assert "pytest" in err
    assert "0022" in err  # cites the doctor remediation path


def test_main_failure_plus_skip_exits_two_with_skip_line(tmp_path: Path, monkeypatch, capsys) -> None:
    ctx = gate.TicketContext(ticket_dir=tmp_path, worktree_dir=tmp_path / "0043-wt")
    monkeypatch.setattr(gate, "discover_tickets_to_gate", lambda _root: [ctx])
    monkeypatch.setattr(
        gate, "collect_report",
        lambda _wt, stacks=None: (["=== python ===\npytest (last 40 lines):\nE   assert 0"],
                                  ["python: skipped (not installed) — staticcheck"]),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    rc = gate.main()
    err = capsys.readouterr().err
    assert rc == 2  # real failure blocks
    assert "blocked completion" in err
    assert "staticcheck" in err  # skip line joins the blocking report


def test_collect_failures_still_returns_failure_sections(tmp_path: Path, monkeypatch) -> None:
    # The existing list[str] contract of collect_failures is preserved.
    monkeypatch.setattr(gate, "collect_report", lambda _wt, stacks=None: (["=== python ===\nboom"], ["python: skipped — x"]))
    assert gate.collect_failures(tmp_path) == ["=== python ===\nboom"]


# ── FR-3: the findings renderer surfaces skips ──────────────────────────────

def _skipped_result() -> GateResult:
    return GateResult(
        gate="staticcheck", passed=True,
        errors=[GateError(
            message="staticcheck not installed — staticcheck gate skipped (install: go install ...)",
            file=None, line=None, column=None, code="TOOL_SKIPPED", severity="warning",
        )],
        duration_ms=0,
    )


def _clean_result(name: str) -> GateResult:
    return GateResult(gate=name, passed=True, errors=[], duration_ms=5)


def test_renderer_emits_skipped_tools_section() -> None:
    lr = LanguageResult(language=StackName.GO, results=[_clean_result("build"), _skipped_result()])
    body = server._format_polyglot_findings([lr], "/tmp")
    assert "## Skipped Tools" in body
    assert "staticcheck" in body
    assert "0022" in body  # doctor remediation path referenced


def test_renderer_skipped_gate_section_reads_clean() -> None:
    # The TOOL_SKIPPED warning is NOT repeated as a per-gate finding.
    lr = LanguageResult(language=StackName.GO, results=[_skipped_result()])
    body = server._format_polyglot_findings([lr], "/tmp")
    assert "clean" in body
    assert "[`TOOL_SKIPPED`]" not in body  # not listed as a per-gate error line


def test_renderer_no_section_without_skips() -> None:
    lr = LanguageResult(language=StackName.PYTHON, results=[_clean_result("lint")])
    body = server._format_polyglot_findings([lr], "/tmp")
    assert "Skipped Tools" not in body


# ── FR-3 / FR-4: documentation wiring ───────────────────────────────────────

def test_gate_md_documents_skipped_tools_section() -> None:
    text = (ROOT / "commands" / "gate.md").read_text(encoding="utf-8")
    assert "Skipped Tools" in text
    assert "TOOL_SKIPPED" in text


def test_build_ticket_step1_surfaces_skipped_tools() -> None:
    text = (ROOT / "context" / "flows" / "build-ticket.md").read_text(encoding="utf-8")
    assert "skipped" in text.lower()
    assert "0022" in text


# ── FR-1 end-to-end: the named tools surface through the server handlers ─────
# The two skip sites (go staticcheck, rust cargo-audit) run only in the text-mode
# suites consumed by gate_run; without these the passing gate's TOOL_SKIPPED
# warning is dropped and the skip stays as silent as before the ticket.

def _failing_result() -> GateResult:
    return GateResult(
        gate="test", passed=False,
        errors=[GateError(message="boom", file=None, line=None, column=None,
                          code="TEST_FAILURE", severity="error")],
        duration_ms=1,
    )


def test_gate_run_surfaces_skipped_tools_on_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "run_suite_for",
        lambda *a, **k: [_clean_result("build"), _skipped_result()],
    )
    out = json.loads(server.gate_run("impl", "tests", "go", "/tmp"))
    assert out["passed"] is True
    assert any("staticcheck" in m for m in out["skipped_tools"])


def test_gate_run_surfaces_skipped_tools_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "run_suite_for",
        lambda *a, **k: [_skipped_result(), _failing_result()],
    )
    out = json.loads(server.gate_run("impl", "tests", "go", "/tmp"))
    assert out["passed"] is False
    assert any("staticcheck" in m for m in out["skipped_tools"])


def test_gate_run_no_skip_omits_key(monkeypatch) -> None:
    # No skip => byte-for-byte-unchanged all-pass response shape.
    monkeypatch.setattr(server, "run_suite_for", lambda *a, **k: [_clean_result("build")])
    out = json.loads(server.gate_run("impl", "tests", "go", "/tmp"))
    assert out == {"passed": True, "duration_ms": 5}


def test_gate_run_on_dir_renders_skipped_tools_section(monkeypatch) -> None:
    # Directory mode: a TOOL_SKIPPED warning on an all-pass single-language run must
    # still emit findings_md carrying the ## Skipped Tools section (m1).
    monkeypatch.setattr(
        server, "run_suite_on_dir",
        lambda *a, **k: [_clean_result("build"), _skipped_result()],
    )
    out = json.loads(server.gate_run_on_dir("/tmp", "go", "/tmp"))
    assert out["passed"] is True
    assert "## Skipped Tools" in out["findings_md"]
    assert "staticcheck" in out["findings_md"]
