"""Tests for the coverage enforcement gate (ticket 0011).

The gate's logic is exercised deterministically through the injected ``_runner``
seam plus narrow monkeypatches of ``coverage._git`` (git plumbing),
``coverage.shutil.which`` (tool detection) and ``coverage.load_thresholds``
(threshold config) — never ``subprocess`` itself. Real-tool paths (pytest-cov /
nyc / cargo-llvm-cov) are ``importorskip``-guarded so the suite stays green where
those tools are not installed.
"""
from __future__ import annotations

import inspect
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gates import coverage
from gates.coverage import (
    BASE_COVERAGE_RUN_FAILED,
    BASE_MERGE_BASE_FAILED,
    BASE_WORKTREE_FAILED,
    COVERAGE_BELOW_THRESHOLD,
    COVERAGE_CONFIG_ERROR,
    COVERAGE_PARSE_ERROR,
    COVERAGE_TOOL_MISSING,
    COVERAGE_TOOL_TIMEOUT,
    CoverageConfigError,
    load_thresholds,
    run_coverage_gate,
)
from models import GateResult


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _fake_git(*, merge_ok: bool = True, add_ok: bool = True):
    """A stand-in for coverage._git that simulates the base-worktree plumbing."""
    def _git(directory: str, args: list[str], timeout_s: int):
        if args[0] == "merge-base":
            return _proc(stdout="abcdef1234567890\n") if merge_ok else None
        if args[:2] == ["worktree", "add"]:
            return _proc(returncode=0 if add_ok else 1)
        return _proc(returncode=0)  # worktree remove
    return _git


@pytest.fixture
def ticket_env(tmp_path):
    """A tmp project with a .tickets/ dir, an active ticket, and a standards file."""
    tickets = tmp_path / ".tickets"
    ticket_dir = tickets / "0011-slug"
    ticket_dir.mkdir(parents=True)
    (tickets / ".active").write_text("0011-slug", encoding="utf-8")
    standards = tickets / "_standards.md"
    standards.write_text("# standards\n", encoding="utf-8")
    return SimpleNamespace(root=tmp_path, tickets=tickets, ticket_dir=ticket_dir, standards=standards)


@pytest.fixture
def thresholds_python(monkeypatch):
    """Force a Python floor of 80 and a present tool, decoupled from the env.

    Patches the tool-detection seam so the measurement path runs deterministically
    whether or not pytest-cov is installed; tests that want the tool *absent*
    re-patch ``_detect_tool`` in their own body.
    """
    monkeypatch.setattr(coverage, "load_thresholds", lambda _sp: {"min_coverage_python": 80})
    monkeypatch.setattr(coverage, "_detect_tool", lambda _lang: "pytest")


@pytest.fixture
def no_delta(monkeypatch):
    """Make the base-branch lookup fail so delta is None and no base run occurs."""
    monkeypatch.setattr(coverage, "_git", lambda *a, **k: None)


def _sidecar(ticket_env) -> dict:
    return json.loads((ticket_env.ticket_dir / "gate-findings.json").read_text(encoding="utf-8"))


# ── FR-8: exports & signature ─────────────────────────────────────────────────

def test_exports_are_callable():
    assert callable(run_coverage_gate)
    assert callable(load_thresholds)


def test_run_coverage_gate_signature():
    params = inspect.signature(run_coverage_gate).parameters
    assert list(params)[:4] == ["directory", "language", "standards_path", "base_ref"]
    assert params["timeout_s"].default == 300
    assert params["_runner"].kind == inspect.Parameter.KEYWORD_ONLY


# ── FR-2: threshold configuration ─────────────────────────────────────────────

def test_load_thresholds_absent_file(tmp_path):
    assert load_thresholds(tmp_path / "_standards.md") == {}


def test_load_thresholds_present(tmp_path):
    pytest.importorskip("yaml")
    (tmp_path / "_thresholds.yaml").write_text(
        "min_coverage_python: 80\nmin_coverage_js: 70\n", encoding="utf-8")
    result = load_thresholds(tmp_path / "_standards.md")
    assert result["min_coverage_python"] == 80
    assert result["min_coverage_js"] == 70


def test_load_thresholds_key_absent(tmp_path):
    pytest.importorskip("yaml")
    (tmp_path / "_thresholds.yaml").write_text("min_coverage_rust: 60\n", encoding="utf-8")
    result = load_thresholds(tmp_path / "_standards.md")
    assert "min_coverage_python" not in result
    assert result["min_coverage_rust"] == 60


def test_load_thresholds_invalid_yaml(tmp_path):
    pytest.importorskip("yaml")
    (tmp_path / "_thresholds.yaml").write_text("min_coverage_python: [unterminated\n", encoding="utf-8")
    with pytest.raises(CoverageConfigError):
        load_thresholds(tmp_path / "_standards.md")


def test_load_thresholds_pyyaml_missing_raises(tmp_path, monkeypatch):
    (tmp_path / "_thresholds.yaml").write_text("min_coverage_python: 80\n", encoding="utf-8")
    # Setting sys.modules['yaml'] = None makes `import yaml` raise ImportError even
    # if PyYAML happens to be installed — a deterministic stand-in for its absence.
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(CoverageConfigError):
        load_thresholds(tmp_path / "_standards.md")


# ── FR-3: argument-list command construction & tool detection ─────────────────

def test_build_command_python_has_directory_element(tmp_path):
    cmd = coverage._build_command("python", str(tmp_path), "pytest")
    assert cmd[0] == sys.executable
    assert cmd[1:3] == ["-m", "pytest"]
    assert str(tmp_path) in cmd  # directory is a discrete list element
    assert "--cov=." in cmd
    assert all(isinstance(part, str) for part in cmd)


def test_build_command_js_has_directory_element(tmp_path):
    cmd = coverage._build_command("typescript", str(tmp_path), "nyc")
    assert cmd[0] == "nyc"
    assert "--cwd" in cmd
    assert str(tmp_path) in cmd


def test_build_command_rust(tmp_path):
    cmd = coverage._build_command("rust", str(tmp_path), "cargo-llvm-cov")
    assert cmd[:2] == ["cargo", "llvm-cov"]
    assert any(str(tmp_path) in part for part in cmd)  # manifest path element


def test_detect_tool_prefers_nyc(monkeypatch):
    monkeypatch.setattr(coverage.shutil, "which",
                        lambda name: f"/bin/{name}" if name in ("nyc", "c8") else None)
    assert coverage._detect_tool("typescript") == "nyc"


def test_detect_tool_c8_when_only_c8(monkeypatch):
    monkeypatch.setattr(coverage.shutil, "which",
                        lambda name: "/bin/c8" if name == "c8" else None)
    assert coverage._detect_tool("javascript") == "c8"


def test_detect_tool_none_when_absent(monkeypatch):
    monkeypatch.setattr(coverage.shutil, "which", lambda name: None)
    assert coverage._detect_tool("typescript") is None


def test_detect_tool_python_present_when_plugin_installed(monkeypatch):
    monkeypatch.setattr(coverage.importlib.util, "find_spec",
                        lambda name: object() if name == "pytest_cov" else None)
    assert coverage._detect_tool("python") == "pytest"


def test_detect_tool_python_missing_when_plugin_absent(monkeypatch):
    # pytest binary may be present, but without the pytest-cov plugin the gate
    # must skip (FR-6 / NFR-2), not fail-closed on the `--cov` parse error (M1).
    monkeypatch.setattr(coverage.importlib.util, "find_spec", lambda name: None)
    assert coverage._detect_tool("python") is None


# ── FR-5: threshold enforcement + sidecar ─────────────────────────────────────

def test_pass_above_threshold(ticket_env, no_delta, thresholds_python):
    runner = Mock(return_value=_proc(stdout="TOTAL 100 10 90%\n"))
    result = run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards,
                               "main", _runner=runner)
    assert result.passed is True
    assert result.gate == "coverage"
    cov = _sidecar(ticket_env)["coverage"]
    assert cov["passed"] is True
    assert cov["pct"] == 90.0
    assert cov["threshold"] == 80
    assert cov["status"] == "passed"


def test_fail_below_threshold(ticket_env, no_delta, thresholds_python):
    runner = Mock(return_value=_proc(stdout="TOTAL 100 40 70%\n"))
    result = run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards,
                               "main", _runner=runner)
    assert result.passed is False
    assert any(e.code == COVERAGE_BELOW_THRESHOLD for e in result.errors)
    cov = _sidecar(ticket_env)["coverage"]
    assert cov["passed"] is False
    assert cov["pct"] == 70.0
    assert cov["status"] == "failed"


# ── FR-6: tool missing skips ──────────────────────────────────────────────────

def test_tool_missing_skips(ticket_env, monkeypatch, thresholds_python):
    monkeypatch.setattr(coverage, "_detect_tool", lambda _lang: None)  # override the fixture
    runner = Mock()
    result = run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards,
                               "main", _runner=runner)
    assert result.passed is True
    assert any(e.code == COVERAGE_TOOL_MISSING for e in result.errors)
    runner.assert_not_called()
    assert _sidecar(ticket_env)["coverage"]["status"] == "skipped"


# ── FR-10b: timeout skips (not crash) ─────────────────────────────────────────

def test_timeout_skips(ticket_env, no_delta, thresholds_python):
    runner = Mock(side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=1))
    result = run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards,
                               "main", _runner=runner)
    assert result.passed is True
    assert any(e.code == COVERAGE_TOOL_TIMEOUT for e in result.errors)


# ── FR-5b: parse error is fail-closed ─────────────────────────────────────────

def test_parse_error_is_fail_closed(ticket_env, no_delta, thresholds_python):
    runner = Mock(return_value=_proc(stdout="no coverage summary here", returncode=1))
    result = run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards,
                               "main", _runner=runner)
    assert result.passed is False
    assert any(e.code == COVERAGE_PARSE_ERROR for e in result.errors)
    cov = _sidecar(ticket_env)["coverage"]
    assert cov["passed"] is False
    assert cov["status"] == "error"


# ── Skip paths: no threshold, config error ────────────────────────────────────

def test_no_threshold_for_language_skips(ticket_env, monkeypatch):
    monkeypatch.setattr(coverage, "load_thresholds", lambda _sp: {})
    runner = Mock()
    result = run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards,
                               "main", _runner=runner)
    assert result.passed is True
    runner.assert_not_called()
    assert _sidecar(ticket_env)["coverage"]["status"] == "skipped"


def test_config_error_skips(ticket_env, monkeypatch):
    def _boom(_sp):
        raise CoverageConfigError("unparseable")
    monkeypatch.setattr(coverage, "load_thresholds", _boom)
    result = run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards,
                               "main", _runner=Mock())
    assert result.passed is True
    assert any(e.code == COVERAGE_CONFIG_ERROR for e in result.errors)


# ── FR-4: delta vs base branch ────────────────────────────────────────────────

def test_delta_positive(ticket_env, monkeypatch, thresholds_python):
    monkeypatch.setattr(coverage, "_git", _fake_git())
    runner = Mock(side_effect=[_proc(stdout="TOTAL 100 10 90%\n"),
                               _proc(stdout="TOTAL 100 20 80%\n")])
    run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards, "main", _runner=runner)
    assert _sidecar(ticket_env)["coverage"]["delta"] == 10.0
    assert runner.call_count == 2  # current + base measurement only


def test_delta_negative(ticket_env, monkeypatch, thresholds_python):
    monkeypatch.setattr(coverage, "_git", _fake_git())
    runner = Mock(side_effect=[_proc(stdout="TOTAL 100 30 70%\n"),
                               _proc(stdout="TOTAL 100 20 80%\n")])
    run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards, "main", _runner=runner)
    assert _sidecar(ticket_env)["coverage"]["delta"] == -10.0


def test_delta_zero(ticket_env, monkeypatch, thresholds_python):
    monkeypatch.setattr(coverage, "_git", _fake_git())
    runner = Mock(side_effect=[_proc(stdout="TOTAL 100 20 80%\n"),
                               _proc(stdout="TOTAL 100 20 80%\n")])
    run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards, "main", _runner=runner)
    assert _sidecar(ticket_env)["coverage"]["delta"] == 0.0


def test_delta_none_when_no_merge_base(ticket_env, monkeypatch, thresholds_python):
    monkeypatch.setattr(coverage, "_git", _fake_git(merge_ok=False))
    runner = Mock(side_effect=[_proc(stdout="TOTAL 100 10 90%\n")])
    run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards, "main", _runner=runner)
    cov = _sidecar(ticket_env)["coverage"]
    assert cov["delta"] is None
    assert any(w.startswith(BASE_MERGE_BASE_FAILED) for w in cov["warnings"])
    assert runner.call_count == 1


def test_delta_none_when_base_worktree_fails(ticket_env, monkeypatch, thresholds_python):
    monkeypatch.setattr(coverage, "_git", _fake_git(add_ok=False))
    runner = Mock(side_effect=[_proc(stdout="TOTAL 100 10 90%\n")])
    run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards, "main", _runner=runner)
    cov = _sidecar(ticket_env)["coverage"]
    assert cov["delta"] is None
    assert any(w.startswith(BASE_WORKTREE_FAILED) for w in cov["warnings"])
    assert runner.call_count == 1


def test_delta_zero_when_base_run_fails(ticket_env, monkeypatch, thresholds_python):
    monkeypatch.setattr(coverage, "_git", _fake_git())
    runner = Mock(side_effect=[_proc(stdout="TOTAL 100 10 90%\n"),
                               subprocess.TimeoutExpired(cmd="pytest", timeout=1)])
    run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards, "main", _runner=runner)
    cov = _sidecar(ticket_env)["coverage"]
    assert cov["delta"] == 0.0
    assert any(w.startswith(BASE_COVERAGE_RUN_FAILED) for w in cov["warnings"])


# ── FR-7: sidecar schema ──────────────────────────────────────────────────────

def test_sidecar_schema(ticket_env, no_delta, thresholds_python):
    runner = Mock(return_value=_proc(stdout="TOTAL 100 10 90%\n"))
    run_coverage_gate(str(ticket_env.root), "python", ticket_env.standards, "main", _runner=runner)
    cov = _sidecar(ticket_env)["coverage"]
    assert set(cov) == {"passed", "pct", "delta", "threshold", "status", "warnings"}
    assert isinstance(cov["passed"], bool)
    assert isinstance(cov["pct"], float)
    assert isinstance(cov["warnings"], list)
    # gate-findings.md gains a human-readable coverage section.
    md = (ticket_env.ticket_dir / "gate-findings.md").read_text(encoding="utf-8")
    assert "## Coverage" in md


# ── FR-7 / FR-9: wiring into run_suite_on_dir & gate_run_on_dir ────────────────

@pytest.fixture
def _no_dep_audit(monkeypatch):
    """Isolate coverage wiring from the co-resident dep-audit phase (ticket 0012)."""
    monkeypatch.setattr("gates.dep_audit.dep_audit_enabled", lambda directory: False)


def test_run_suite_appends_coverage_after_language_gates(monkeypatch, _no_dep_audit):
    import gates as gates_pkg
    monkeypatch.setattr("gates.python.run_python_suite_on_dir",
                        lambda directory, fail_fast=True, config=None: [
                            GateResult(gate="test", passed=True, errors=[], duration_ms=1)])
    monkeypatch.setattr("gates.coverage.run_coverage_gate",
                        lambda d, lang, sp, br: GateResult(
                            gate="coverage", passed=True, errors=[], duration_ms=1))
    results = gates_pkg.run_suite_on_dir(
        "python", "/proj", standards_path="/proj/.tickets/_standards.md")
    # Coverage is appended after the language gates (the trailing sast phase now
    # runs last, so assert order rather than final position).
    order = [r.gate for r in results]
    assert "coverage" in order
    assert order.index("coverage") > order.index("test")


def test_run_suite_no_coverage_without_standards(monkeypatch, _no_dep_audit):
    import gates as gates_pkg
    monkeypatch.setattr("gates.python.run_python_suite_on_dir",
                        lambda directory, fail_fast=True, config=None: [
                            GateResult(gate="test", passed=True, errors=[], duration_ms=1)])
    results = gates_pkg.run_suite_on_dir("python", "/proj")
    assert all(r.gate != "coverage" for r in results)


def test_run_suite_skips_coverage_for_go(monkeypatch, _no_dep_audit):
    import gates as gates_pkg
    monkeypatch.setattr("gates.go.run_go_suite_on_dir",
                        lambda directory, fail_fast=True, config=None: [
                            GateResult(gate="build", passed=True, errors=[], duration_ms=1)])
    results = gates_pkg.run_suite_on_dir(
        "go", "/proj", standards_path="/proj/.tickets/_standards.md")
    assert all(r.gate != "coverage" for r in results)


def test_run_suite_skips_coverage_when_prior_gate_failed(monkeypatch, _no_dep_audit):
    import gates as gates_pkg
    monkeypatch.setattr("gates.python.run_python_suite_on_dir",
                        lambda directory, fail_fast=True, config=None: [
                            GateResult(gate="lint", passed=False, errors=[], duration_ms=1)])
    results = gates_pkg.run_suite_on_dir(
        "python", "/proj", standards_path="/proj/.tickets/_standards.md")
    assert all(r.gate != "coverage" for r in results)


def test_server_forwards_standards_path_from_gated_dir(monkeypatch, tmp_path):
    # B1 regression: standards_path (and thus the sidecar location) must resolve
    # against the *directory being gated* (the worktree), not project_root.
    pytest.importorskip("mcp")
    import server
    gated_dir = tmp_path / "worktree"
    gated_dir.mkdir()
    project_root = tmp_path / "mainrepo"
    project_root.mkdir()
    captured: dict = {}

    def _fake_suite(stack, directory, fail_fast=True, *, standards_path=None, base_ref="main", config=None):
        captured["standards_path"] = standards_path
        captured["base_ref"] = base_ref
        return [GateResult(gate="test", passed=True, errors=[], duration_ms=1)]

    monkeypatch.setattr(server, "run_suite_on_dir", _fake_suite)
    server.gate_run_on_dir(str(gated_dir), "python", str(project_root))
    assert captured["standards_path"] == str(gated_dir / ".tickets" / "_standards.md")
    assert captured["base_ref"] == "main"


# ── FR-1 / FR-7: real-tool integration (skipped when tools absent) ────────────

def test_integration_python_real_tool(tmp_path, monkeypatch):
    pytest.importorskip("pytest_cov")
    tickets = tmp_path / ".tickets"
    (tickets / "0011-slug").mkdir(parents=True)
    (tickets / ".active").write_text("0011-slug", encoding="utf-8")
    standards = tickets / "_standards.md"
    standards.write_text("# standards\n", encoding="utf-8")
    monkeypatch.setattr(coverage, "load_thresholds", lambda _sp: {"min_coverage_python": 50})
    (tmp_path / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(
        "from mod import add\n\ndef test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8")
    result = run_coverage_gate(str(tmp_path), "python", standards, "main")
    cov = json.loads((tickets / "0011-slug" / "gate-findings.json").read_text())["coverage"]
    assert result.passed is True
    assert cov["pct"] > 0
