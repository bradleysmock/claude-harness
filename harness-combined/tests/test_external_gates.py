"""Tests for gates/external.py — pluggable external gates, SARIF-in (ticket 0077)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from gates.external import MAX_SARIF_RESULTS, ExternalGateSpec, run_external_gate


def _script_command(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "fake_tool.py"
    script.write_text(body, encoding="utf-8")
    return [sys.executable, str(script)]


def _sarif(results: list[dict]) -> str:
    return json.dumps({
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "fake"}}, "results": results}],
    })


# ---------------------------------------------------------------------------
# FR-1 — timeout
# ---------------------------------------------------------------------------

def test_hang_past_timeout_yields_timeout_result(tmp_path: Path):
    command = _script_command(tmp_path, "import time\ntime.sleep(10)\n")
    spec = ExternalGateSpec(name="slow", command=command, scope=None, timeout_seconds=1)
    result = run_external_gate(spec, str(tmp_path))
    assert result.passed is False
    assert result.errors[0].code == "TIMEOUT"


# ---------------------------------------------------------------------------
# FR-2 — path containment
# ---------------------------------------------------------------------------

def test_escaping_absolute_path_becomes_file_none(tmp_path: Path):
    payload = _sarif([{
        "ruleId": "R1", "level": "error",
        "message": {"text": "bad"},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": "/etc/passwd"},
            "region": {"startLine": 1},
        }}],
    }])
    command = _script_command(tmp_path, f"print({payload!r})")
    spec = ExternalGateSpec(name="fake", command=command, scope=None, timeout_seconds=10)
    result = run_external_gate(spec, str(tmp_path))
    assert result.errors[0].file is None


def test_contained_relative_path_resolves(tmp_path: Path):
    payload = _sarif([{
        "ruleId": "R1", "level": "error",
        "message": {"text": "bad"},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": "src/m.py"},
            "region": {"startLine": 3},
        }}],
    }])
    command = _script_command(tmp_path, f"print({payload!r})")
    spec = ExternalGateSpec(name="fake", command=command, scope=None, timeout_seconds=10)
    result = run_external_gate(spec, str(tmp_path))
    assert result.errors[0].file == "src/m.py"
    assert result.errors[0].line == 3


# ---------------------------------------------------------------------------
# FR-3 — TOOL_ERROR classification
# ---------------------------------------------------------------------------

def test_empty_runs_passes(tmp_path: Path):
    payload = _sarif([])
    command = _script_command(tmp_path, f"print({payload!r})")
    spec = ExternalGateSpec(name="fake", command=command, scope=None, timeout_seconds=10)
    result = run_external_gate(spec, str(tmp_path))
    assert result.passed is True


def test_malformed_stdout_is_tool_error(tmp_path: Path):
    command = _script_command(tmp_path, "print('not json at all')")
    spec = ExternalGateSpec(name="fake", command=command, scope=None, timeout_seconds=10)
    result = run_external_gate(spec, str(tmp_path))
    assert result.passed is False
    assert result.errors[0].code == "TOOL_ERROR"


def test_absent_stdout_is_tool_error(tmp_path: Path):
    command = _script_command(tmp_path, "pass")
    spec = ExternalGateSpec(name="fake", command=command, scope=None, timeout_seconds=10)
    result = run_external_gate(spec, str(tmp_path))
    assert result.passed is False
    assert result.errors[0].code == "TOOL_ERROR"


def test_oversize_results_is_tool_error(tmp_path: Path):
    many = [{"ruleId": "R", "level": "error", "message": {"text": "x"}, "locations": []}] * (
        MAX_SARIF_RESULTS + 1
    )
    payload = _sarif(many)
    command = _script_command(tmp_path, f"print({payload!r})")
    spec = ExternalGateSpec(name="fake", command=command, scope=None, timeout_seconds=10)
    result = run_external_gate(spec, str(tmp_path))
    assert result.passed is False
    assert result.errors[0].code == "TOOL_ERROR"


def test_nonzero_exit_with_valid_sarif_is_not_tool_error(tmp_path: Path):
    payload = _sarif([{
        "ruleId": "R1", "level": "error", "message": {"text": "found something"},
        "locations": [],
    }])
    command = _script_command(
        tmp_path, f"import sys\nprint({payload!r})\nsys.exit(1)\n"
    )
    spec = ExternalGateSpec(name="fake", command=command, scope=None, timeout_seconds=10)
    result = run_external_gate(spec, str(tmp_path))
    assert result.passed is False
    assert result.errors[0].code == "R1"  # a real finding, not TOOL_ERROR


def test_finding_fails_the_gate(tmp_path: Path):
    payload = _sarif([{
        "ruleId": "R1", "level": "error", "message": {"text": "found something"},
        "locations": [],
    }])
    command = _script_command(tmp_path, f"print({payload!r})")
    spec = ExternalGateSpec(name="fake", command=command, scope=None, timeout_seconds=10)
    result = run_external_gate(spec, str(tmp_path))
    assert result.passed is False
    assert result.errors[0].message == "found something"


def test_missing_binary_is_tool_error(tmp_path: Path):
    spec = ExternalGateSpec(
        name="fake", command=["definitely-not-a-real-binary-xyz"],
        scope=None, timeout_seconds=10,
    )
    result = run_external_gate(spec, str(tmp_path))
    assert result.passed is False
    assert result.errors[0].code == "TOOL_ERROR"
