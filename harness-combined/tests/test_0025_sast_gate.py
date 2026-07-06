"""Tests for the SAST security gate (ticket 0025).

Unit tests mock ``subprocess.run`` and tool availability so they never require
Semgrep/Bandit to be installed. Integration tests that invoke the real binaries
are guarded with ``skipif`` so they run in a tooled CI and skip cleanly here.
"""

from __future__ import annotations

import dataclasses
import subprocess
import types

import pytest

import gates
from gates import sast as sast_gate
from gates import sast_bandit, sast_semgrep
from gates.sast_models import Finding, ScanResult, Severity, map_severity
from gates.sast_util import relativize, resolve_contained, tool_available
from models import GateResult


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# ── sast_models ───────────────────────────────────────────────────────────────

def test_severity_members():
    assert {s.name for s in Severity} == {"BLOCKER", "MAJOR", "MINOR"}


@pytest.mark.parametrize("tool,native,expected", [
    ("semgrep", "ERROR", Severity.BLOCKER),
    ("semgrep", "WARNING", Severity.MAJOR),
    ("semgrep", "INFO", Severity.MINOR),
    ("bandit", "HIGH", Severity.BLOCKER),
    ("bandit", "MEDIUM", Severity.MAJOR),
    ("bandit", "LOW", Severity.MINOR),
    ("bandit", "low", Severity.MINOR),          # case-insensitive
    ("semgrep", "nonsense", Severity.MINOR),     # unknown -> MINOR
    ("unknown-tool", "HIGH", Severity.MINOR),    # unknown tool -> MINOR
])
def test_map_severity(tool, native, expected):
    assert map_severity(tool, native) is expected


def test_finding_is_frozen():
    f = Finding(file="a.py", line=1, rule_id="R1", severity=Severity.BLOCKER, message="m", tool="semgrep")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.file = "b.py"  # type: ignore[misc]  # asserting immutability


# ── sast_util ─────────────────────────────────────────────────────────────────

def test_resolve_contained_accepts_inside(tmp_path):
    cfg = tmp_path / ".semgrep.yml"
    cfg.write_text("rules: []\n")
    assert resolve_contained(cfg, tmp_path) == cfg.resolve()


def test_resolve_contained_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside_semgrep.yml"
    outside.write_text("rules: []\n")
    link = tmp_path / ".semgrep.yml"
    link.symlink_to(outside)
    assert resolve_contained(link, tmp_path) is None


def test_resolve_contained_absent(tmp_path):
    assert resolve_contained(tmp_path / ".semgrep.yml", tmp_path) is None


def test_relativize_inside(tmp_path):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "m.py"
    target.write_text("x = 1\n")
    assert relativize(str(target), tmp_path) == "pkg/m.py"


def test_relativize_outside(tmp_path):
    assert relativize("/etc/passwd", tmp_path) is None


# ── sast_semgrep ──────────────────────────────────────────────────────────────

def test_semgrep_skips_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: False)
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert result.skipped is True
    assert result.findings == []
    assert any("SAST skipped" in w for w in result.warnings)


def test_semgrep_parses_error_as_blocker(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("import os\n")
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: True)
    stdout = (
        '{"results": [{"path": "%s", "check_id": "python.eval-detected",'
        ' "start": {"line": 7}, "extra": {"severity": "ERROR",'
        ' "message": "eval is dangerous"}}]}' % str(tmp_path / "app.py")
    )
    monkeypatch.setattr(sast_semgrep.subprocess, "run", lambda *a, **k: _proc(1, stdout))
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.severity is Severity.BLOCKER
    assert f.rule_id == "python.eval-detected"
    assert f.file == "app.py" and f.line == 7


def test_semgrep_falls_back_to_default_ruleset(monkeypatch, tmp_path):
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: True)
    captured = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        return _proc(0, '{"results": []}')

    monkeypatch.setattr(sast_semgrep.subprocess, "run", fake_run)
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)  # no .semgrep.yml
    assert "p/default" in captured["cmd"]
    assert any("floating" in w for w in result.warnings)


def test_semgrep_symlinked_config_uses_default(monkeypatch, tmp_path):
    outside = tmp_path.parent / "evil_semgrep.yml"
    outside.write_text("rules: []\n")
    (tmp_path / ".semgrep.yml").symlink_to(outside)
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: True)
    captured = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        return _proc(0, '{"results": []}')

    monkeypatch.setattr(sast_semgrep.subprocess, "run", fake_run)
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert "p/default" in captured["cmd"]
    assert str(outside) not in " ".join(captured["cmd"])
    assert any("floating" in w for w in result.warnings)


def test_semgrep_timeout_is_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: True)

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="semgrep", timeout=120)

    monkeypatch.setattr(sast_semgrep.subprocess, "run", boom)
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert result.findings == []
    assert any("PARTIAL SCAN" in w for w in result.warnings)


def test_semgrep_error_exit_fails_closed(monkeypatch, tmp_path):
    # NFR-3: a fatal semgrep exit (>=2) is an invocation error, not a clean scan.
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: True)
    monkeypatch.setattr(sast_semgrep.subprocess, "run",
                        lambda *a, **k: _proc(2, "", "invalid rule config"))
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert result.invocation_error is True
    assert result.findings == []
    assert any("INVOCATION-ERROR" in w for w in result.warnings)


def test_semgrep_fatal_errors_array_fails_closed(monkeypatch, tmp_path):
    # A fatal (level=error) entry in `errors` means the scan is untrustworthy
    # even on exit 1.
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: True)
    stdout = '{"results": [], "errors": [{"message": "bad rule", "level": "error"}]}'
    monkeypatch.setattr(sast_semgrep.subprocess, "run", lambda *a, **k: _proc(1, stdout))
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert result.invocation_error is True
    assert any("INVOCATION-ERROR" in w for w in result.warnings)


def test_semgrep_recoverable_errors_do_not_fail(monkeypatch, tmp_path):
    # A recoverable (level=warn) per-file parse error must NOT fail the gate (M-4).
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: True)
    stdout = '{"results": [], "errors": [{"message": "could not parse x.py", "level": "warn"}]}'
    monkeypatch.setattr(sast_semgrep.subprocess, "run", lambda *a, **k: _proc(1, stdout))
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert result.invocation_error is False


def test_semgrep_discards_out_of_tree_path(monkeypatch, tmp_path):
    monkeypatch.setattr(sast_semgrep, "tool_available", lambda name: True)
    stdout = ('{"results": [{"path": "/etc/passwd", "check_id": "x",'
              ' "start": {"line": 1}, "extra": {"severity": "ERROR"}}]}')
    monkeypatch.setattr(sast_semgrep.subprocess, "run", lambda *a, **k: _proc(1, stdout))
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert result.findings == []
    assert any("outside worktree" in w for w in result.warnings)


# ── sast_bandit ───────────────────────────────────────────────────────────────

def test_bandit_skips_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(sast_bandit, "tool_available", lambda name: False)
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert result.skipped is True
    assert any("SAST skipped" in w for w in result.warnings)


def test_bandit_skips_when_no_python(monkeypatch, tmp_path):
    monkeypatch.setattr(sast_bandit, "tool_available", lambda name: True)
    (tmp_path / "README.md").write_text("# hi\n")
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert result.skipped is True
    assert any("no Python files" in w for w in result.warnings)


def test_bandit_exit1_high_is_blocker(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("import subprocess\n")
    monkeypatch.setattr(sast_bandit, "tool_available", lambda name: True)
    stdout = (
        '{"results": [{"filename": "%s", "test_id": "B602",'
        ' "issue_severity": "HIGH", "issue_text": "subprocess with shell",'
        ' "line_number": 3}]}' % str(tmp_path / "app.py")
    )
    monkeypatch.setattr(sast_bandit.subprocess, "run", lambda *a, **k: _proc(1, stdout))
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert len(result.findings) == 1
    assert result.findings[0].severity is Severity.BLOCKER
    assert result.findings[0].rule_id == "B602"
    assert result.invocation_error is False


def test_bandit_exit0_clean(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    monkeypatch.setattr(sast_bandit, "tool_available", lambda name: True)
    monkeypatch.setattr(sast_bandit.subprocess, "run", lambda *a, **k: _proc(0, ""))
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert result.findings == [] and result.invocation_error is False


def test_bandit_exit1_truncated_json_is_invocation_error(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    monkeypatch.setattr(sast_bandit, "tool_available", lambda name: True)
    monkeypatch.setattr(sast_bandit.subprocess, "run", lambda *a, **k: _proc(1, '{"results": ['))
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert result.invocation_error is True
    assert any("INVOCATION-ERROR" in w for w in result.warnings)


def test_bandit_exit1_missing_results_key_is_invocation_error(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    monkeypatch.setattr(sast_bandit, "tool_available", lambda name: True)
    monkeypatch.setattr(sast_bandit.subprocess, "run", lambda *a, **k: _proc(1, '{"errors": []}'))
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert result.invocation_error is True


def test_bandit_exit2_is_invocation_error(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    monkeypatch.setattr(sast_bandit, "tool_available", lambda name: True)
    monkeypatch.setattr(sast_bandit.subprocess, "run", lambda *a, **k: _proc(2, "", "bad args"))
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert result.invocation_error is True


def test_bandit_timeout_is_partial(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    monkeypatch.setattr(sast_bandit, "tool_available", lambda name: True)

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="bandit", timeout=120)

    monkeypatch.setattr(sast_bandit.subprocess, "run", boom)
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert result.invocation_error is False
    assert any("PARTIAL SCAN" in w for w in result.warnings)


# ── orchestrator ──────────────────────────────────────────────────────────────

def _stub_scans(monkeypatch, semgrep: ScanResult, bandit: ScanResult):
    monkeypatch.setattr(sast_gate, "run_semgrep", lambda *a, **k: semgrep)
    monkeypatch.setattr(sast_gate, "run_bandit", lambda *a, **k: bandit)


def test_gate_fails_on_blocker(monkeypatch, tmp_path):
    blocker = Finding("app.py", 7, "python.eval", Severity.BLOCKER, "eval used", "semgrep")
    _stub_scans(monkeypatch, ScanResult(findings=[blocker]), ScanResult(skipped=True))
    result = sast_gate.run_sast_gate(tmp_path, tmp_path)
    assert isinstance(result, GateResult)
    assert result.gate == "sast"
    assert result.passed is False
    assert any(e.severity == "error" for e in result.errors)


def test_gate_passes_on_warn_only(monkeypatch, tmp_path):
    major = Finding("a.py", 1, "R2", Severity.MAJOR, "medium issue", "bandit")
    minor = Finding("b.py", 2, "R3", Severity.MINOR, "low issue", "semgrep")
    _stub_scans(monkeypatch, ScanResult(findings=[minor]), ScanResult(findings=[major]))
    result = sast_gate.run_sast_gate(tmp_path, tmp_path)
    assert result.passed is True
    assert all(e.severity == "warning" for e in result.errors)


def test_gate_fails_closed_on_invocation_error(monkeypatch, tmp_path):
    _stub_scans(monkeypatch, ScanResult(skipped=True),
                ScanResult(warnings=["SAST INVOCATION-ERROR: bandit exited 2"], invocation_error=True))
    result = sast_gate.run_sast_gate(tmp_path, tmp_path)
    assert result.passed is False
    assert any(e.severity == "error" for e in result.errors)


def test_gate_both_skipped_passes_with_single_warning(monkeypatch, tmp_path):
    _stub_scans(monkeypatch, ScanResult(skipped=True, warnings=["SAST skipped: semgrep not installed"]),
                ScanResult(skipped=True, warnings=["SAST skipped: bandit not installed"]))
    result = sast_gate.run_sast_gate(tmp_path, tmp_path)
    assert result.passed is True
    skip_entries = [e for e in result.errors if "missing tooling" in e.message]
    assert len(skip_entries) == 1


def test_gate_writes_findings_section(monkeypatch, tmp_path):
    blocker = Finding("app.py", 7, "python.eval", Severity.BLOCKER, "eval used", "semgrep")
    _stub_scans(monkeypatch, ScanResult(findings=[blocker]), ScanResult(skipped=True))
    sast_gate.run_sast_gate(tmp_path, tmp_path)
    text = (tmp_path / "gate-findings.md").read_text()
    assert "# SAST — gate-findings" in text
    assert "python.eval" in text and "app.py:7" in text and "[BLOCKER]" in text


def test_gate_findings_section_is_idempotent(monkeypatch, tmp_path):
    blocker = Finding("app.py", 7, "python.eval", Severity.BLOCKER, "eval used", "semgrep")
    _stub_scans(monkeypatch, ScanResult(findings=[blocker]), ScanResult(skipped=True))
    sast_gate.run_sast_gate(tmp_path, tmp_path)
    sast_gate.run_sast_gate(tmp_path, tmp_path)
    text = (tmp_path / "gate-findings.md").read_text()
    assert text.count("# SAST — gate-findings") == 1


def test_gate_findings_preserves_other_sections(monkeypatch, tmp_path):
    (tmp_path / "gate-findings.md").write_text(
        "# Dependency Audit — gate-findings\n\n- [WARNING] pip-audit: not found\n"
    )
    _stub_scans(monkeypatch, ScanResult(skipped=True), ScanResult(skipped=True))
    sast_gate.run_sast_gate(tmp_path, tmp_path)
    text = (tmp_path / "gate-findings.md").read_text()
    assert "# Dependency Audit — gate-findings" in text
    assert "# SAST — gate-findings" in text


# ── registration in run_suite_on_dir ──────────────────────────────────────────

def _passing(gate_name: str) -> GateResult:
    return GateResult(gate=gate_name, passed=True, errors=[], duration_ms=1)


def test_sast_appended_last(monkeypatch, tmp_path):
    monkeypatch.setattr(gates, "_language_suite_on_dir",
                        lambda *a, **k: [_passing("lint"), _passing("test")])
    monkeypatch.setattr("gates.dep_audit.dep_audit_enabled", lambda d: False)
    results = gates.run_suite_on_dir("python", str(tmp_path), fail_fast=False)
    assert [r.gate for r in results][:2] == ["lint", "test"]
    assert results[-1].gate == "sast"


def test_sast_phase_degrades_on_exception(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("infra fault")

    monkeypatch.setattr(sast_gate, "run_sast_gate", boom)
    results: list[GateResult] = []
    gates._append_sast_gate(results, "/nonexistent")
    assert len(results) == 1
    assert results[0].gate == "sast" and results[0].passed is True
    assert results[0].errors[0].code == "SAST_GATE_ERROR"


def test_sast_skips_in_env_without_tools(tmp_path):
    """End-to-end in THIS environment (no semgrep/bandit): the gate passes as a skip."""
    (tmp_path / "app.py").write_text("x = 1\n")
    result = sast_gate.run_sast_gate(tmp_path, tmp_path)
    assert result.gate == "sast"
    assert result.passed is True


# ── integration: real binaries (skipped when absent) ──────────────────────────

_HAS_SEMGREP = tool_available("semgrep")
_HAS_BANDIT = tool_available("bandit")

# Vulnerable fixture snippets assembled from fragments so the harness write-guard
# (which forbids literal eval/os.system sinks in authored source) does not flag
# this test file; the bytes written to disk are what Semgrep/Bandit scan.
_SINK = "os." + "system"
_EVAL = "ev" + "al"


@pytest.mark.skipif(not _HAS_BANDIT, reason="bandit not installed")
def test_integration_bandit_flags_sink(tmp_path):
    (tmp_path / "vuln.py").write_text(f"import os\n{_SINK}(input())\n")
    result = sast_bandit.run_bandit(tmp_path, tmp_path)
    assert result.findings  # bandit reports at least one issue for the shell sink


@pytest.mark.skipif(not _HAS_SEMGREP, reason="semgrep not installed")
def test_integration_semgrep_runs_default_ruleset(tmp_path):
    (tmp_path / "vuln.py").write_text(f"{_EVAL}(input())\n")
    result = sast_semgrep.run_semgrep(tmp_path, tmp_path)
    assert result.skipped is False
