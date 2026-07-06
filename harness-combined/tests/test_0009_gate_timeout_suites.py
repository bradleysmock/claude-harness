"""Integration tests: GateTimeoutConfig is forwarded through every language suite
and a subprocess TimeoutExpired is reported as a TIMEOUT GateResult (FR-4).

The test gate of each language is exercised directly with subprocess.run patched to
raise TimeoutExpired, so the assertion pins config forwarding + timeout resolution +
the shared message contract across python/typescript/go/rust — guarding against a
silent config-forwarding regression in any one module.
"""
from __future__ import annotations

import subprocess

import pytest

import gates
import gates.go as go
import gates.python as python
import gates.rust as rust
import gates.typescript as typescript
from gates import GateTimeoutConfig
from models import GateResult


def _raise_timeout(cmd, *args, **kwargs):
    raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))


# (label, module-under-patch, test-gate callable taking (directory, config))
_TEST_GATES = [
    ("python", python, python._test_gate_dir),
    ("typescript", typescript, typescript._test_gate_dir),
    ("go", go, go._test_gate),
    ("rust", rust, rust._test_gate),
]


@pytest.mark.parametrize(
    "label,module,gate", _TEST_GATES, ids=[c[0] for c in _TEST_GATES]
)
def test_test_gate_reports_configured_timeout(label, module, gate, monkeypatch, tmp_path):
    monkeypatch.setattr(module.subprocess, "run", _raise_timeout)
    cfg = GateTimeoutConfig(test_timeout_seconds=5)
    res = gate(str(tmp_path), cfg)
    assert res.gate == "test"
    assert res.passed is False
    assert res.errors[0].code == "TIMEOUT"
    assert res.errors[0].message == "test gate timed out after 5 s"


@pytest.mark.parametrize(
    "label,module,gate,hardcoded",
    [
        ("python", python, python._test_gate_dir, 180),
        ("typescript", typescript, typescript._test_gate_dir, 180),
        ("go", go, go._test_gate, 120),
        ("rust", rust, rust._test_gate, 180),
    ],
    ids=["python", "typescript", "go", "rust"],
)
def test_test_gate_none_config_uses_hardcoded_default(
    label, module, gate, hardcoded, monkeypatch, tmp_path
):
    monkeypatch.setattr(module.subprocess, "run", _raise_timeout)
    res = gate(str(tmp_path), None)
    assert res.errors[0].message == f"test gate timed out after {hardcoded} s"


def test_configured_timeout_is_passed_to_subprocess_run(monkeypatch, tmp_path):
    """Acceptance: test_timeout_seconds=30 -> subprocess.run(..., timeout=30)."""
    captured = {}

    def recording_run(cmd, *args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(python.subprocess, "run", recording_run)
    res = python._test_gate_dir(str(tmp_path), GateTimeoutConfig(test_timeout_seconds=30))
    assert captured["timeout"] == 30
    assert res.passed is True


def test_global_default_passed_to_subprocess_run(monkeypatch, tmp_path):
    """Acceptance: default_timeout_seconds=45 -> lint/typecheck get timeout=45."""
    captured = {}

    def recording_run(cmd, *args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(python.subprocess, "run", recording_run)
    python._lint_gate_dir(str(tmp_path), GateTimeoutConfig(default_timeout_seconds=45))
    assert captured["timeout"] == 45


def test_run_python_suite_reaches_test_gate_timeout(monkeypatch):
    """Full python suite: earlier gates pass, only pytest times out (FR-4 literal)."""

    def fake_run(cmd, *args, **kwargs):
        if "pytest" in cmd:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(python.subprocess, "run", fake_run)
    impl = "def add(a, b):\n    return a + b\n"
    tests = "def test_add():\n    assert True\n"
    results = python.run_python_suite(
        impl, tests, ".", config=GateTimeoutConfig(test_timeout_seconds=5)
    )
    last = results[-1]
    assert last.gate == "test"
    assert last.passed is False
    assert last.errors[0].code == "TIMEOUT"
    assert last.errors[0].message == "test gate timed out after 5 s"


def test_run_suite_for_forwards_config_to_language_suite(monkeypatch):
    """FR-6: run_suite_for threads config into the language suite it dispatches to."""
    captured = {}

    def fake_python_suite(implementation, tests, project_root, config=None):
        captured["config"] = config
        return [GateResult(gate="syntax", passed=True, errors=[], duration_ms=1)]

    monkeypatch.setattr(python, "run_python_suite", fake_python_suite)
    cfg = GateTimeoutConfig(test_timeout_seconds=7)
    gates.run_suite_for("python", "impl", "tests", ".", config=cfg)
    assert captured["config"] is cfg


def test_run_suite_on_dir_forwards_config_to_language_suite(monkeypatch):
    """FR-6: run_suite_on_dir threads config into the language suite it dispatches to."""
    captured = {}

    def fake_python_dir(directory, fail_fast=True, config=None):
        captured["config"] = config
        return [GateResult(gate="lint", passed=True, errors=[], duration_ms=1)]

    monkeypatch.setattr(python, "run_python_suite_on_dir", fake_python_dir)
    cfg = GateTimeoutConfig(default_timeout_seconds=42)
    gates.run_suite_on_dir("python", ".", config=cfg)
    assert captured["config"] is cfg


def test_run_python_suite_none_config_unchanged(monkeypatch):
    """FR-5 regression guard: config=None still reaches the test gate at 120 s."""

    def fake_run(cmd, *args, **kwargs):
        if "pytest" in cmd:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(python.subprocess, "run", fake_run)
    results = python.run_python_suite("x = 1\n", "def test_x():\n    assert True\n", ".")
    last = results[-1]
    assert last.gate == "test"
    assert last.errors[0].message == "test gate timed out after 120 s"
