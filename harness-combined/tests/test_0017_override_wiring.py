"""Ticket 0017 — directory-mode gate suites apply operator command overrides."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gates
from gates import python as pymod
from gates.python import run_python_suite_on_dir
from models import GateResult


def test_override_argv_is_run_without_shell(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        captured["shell"] = kw.get("shell", False)
        return SimpleNamespace(stdout="", stderr="", returncode=2)

    monkeypatch.setattr(gates.subprocess, "run", fake_run)
    results = run_python_suite_on_dir(
        str(tmp_path), fail_fast=True, overrides={"lint": ["ruff", "check", "."]}
    )
    assert captured["argv"] == ["ruff", "check", "."]
    assert captured["shell"] is False
    # returncode 2 with no parsed findings -> TOOL_ERROR, and fail-fast stops here.
    assert results[0].gate == "lint"
    assert results[0].passed is False
    assert results[0].errors[0].code == "TOOL_ERROR"
    assert len(results) == 1


def test_override_success_passes_through(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        gates.subprocess, "run",
        lambda argv, **kw: SimpleNamespace(stdout="", stderr="", returncode=0),
    )
    ov = {
        "lint": ["ruff"], "type_check": ["mypy"],
        "test": ["pytest"], "security": ["bandit"],
    }
    results = run_python_suite_on_dir(str(tmp_path), overrides=ov)
    assert [r.gate for r in results] == ["lint", "type_check", "test", "security"]
    assert all(r.passed for r in results)


def test_default_gates_run_when_no_overrides(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def _stub(name):
        def _fn(directory, config):
            calls.append(name)
            return GateResult(name, True, [], 1)
        return _fn

    monkeypatch.setattr(pymod, "_lint_gate_dir", _stub("lint"))
    monkeypatch.setattr(pymod, "_type_check_gate_dir", _stub("type_check"))
    monkeypatch.setattr(pymod, "_test_gate_dir", _stub("test"))
    monkeypatch.setattr(pymod, "_security_gate_dir", _stub("security"))
    results = run_python_suite_on_dir(str(tmp_path))
    assert calls == ["lint", "type_check", "test", "security"]
    assert all(r.passed for r in results)


def test_missing_override_executable_yields_tool_error(monkeypatch, tmp_path: Path) -> None:
    def _boom(argv, **kw):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(gates.subprocess, "run", _boom)
    results = run_python_suite_on_dir(
        str(tmp_path), fail_fast=True, overrides={"lint": ["nonexistent-tool"]}
    )
    assert results[0].passed is False
    assert results[0].errors[0].code == "TOOL_ERROR"
