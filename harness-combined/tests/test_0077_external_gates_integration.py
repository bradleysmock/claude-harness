"""Ticket 0077 — end-to-end wiring: server.py CONFIG_ERROR shape, and
run_suite_on_dir appending an external gate's result (FR-5/FR-6)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import server
from gates import run_suite_on_dir
from gates.external import ExternalGateSpec


def _init_python_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("x: int = 1\n", encoding="utf-8")
    return tmp_path


def test_malformed_external_gates_entry_produces_config_error_shape(tmp_path: Path):
    project = _init_python_project(tmp_path)
    tickets_dir = project / ".tickets"
    tickets_dir.mkdir()
    (tickets_dir / "_standards.md").write_text(
        '```gates\n[external_gates]\n'
        'test = { command = "snyk test" }\n'  # collides with built-in "test"
        '```\n',
        encoding="utf-8",
    )
    response = json.loads(
        server.gate_run_on_dir(str(project), "python", str(project), fail_fast=False)
    )
    assert response["passed"] is False
    assert response["gates"][0]["gate"] == "config"
    assert response["gates"][0]["errors"][0]["code"] == "CONFIG_ERROR"


def test_fixture_sarif_script_appears_in_results(tmp_path: Path):
    project = _init_python_project(tmp_path)
    script = project / "fake_scanner.py"
    payload = json.dumps({
        "version": "2.1.0",
        "runs": [{"results": [{
            "ruleId": "R1", "level": "error", "message": {"text": "planted finding"},
            "locations": [],
        }]}],
    })
    script.write_text(f"print({payload!r})\n", encoding="utf-8")
    spec = ExternalGateSpec(
        name="fakescan", command=[sys.executable, str(script)],
        scope=None, timeout_seconds=10,
    )
    results = run_suite_on_dir("python", str(project), fail_fast=False, external_gates=[spec])
    by_gate = {r.gate: r for r in results}
    assert "fakescan" in by_gate
    assert by_gate["fakescan"].passed is False
    assert by_gate["fakescan"].errors[0].message == "planted finding"


def test_scope_mismatched_external_gate_is_skipped(tmp_path: Path):
    project = _init_python_project(tmp_path)
    spec = ExternalGateSpec(
        name="tsonly", command=[sys.executable, "-c", "print('should not run')"],
        scope="*.ts", timeout_seconds=10,
    )
    results = run_suite_on_dir(
        "python", str(project), fail_fast=False, external_gates=[spec], changed_files=["a.py"],
    )
    by_gate = {r.gate: r for r in results}
    assert by_gate["tsonly"].skipped is True
    assert by_gate["tsonly"].passed is True


def test_external_gate_tool_error_never_degraded_to_pass(tmp_path: Path):
    project = _init_python_project(tmp_path)
    spec = ExternalGateSpec(
        name="broken", command=["definitely-not-a-real-binary-xyz"],
        scope=None, timeout_seconds=10,
    )
    results = run_suite_on_dir("python", str(project), fail_fast=False, external_gates=[spec])
    by_gate = {r.gate: r for r in results}
    assert by_gate["broken"].passed is False
    assert by_gate["broken"].errors[0].code == "TOOL_ERROR"


def test_no_external_gates_block_is_byte_identical(tmp_path: Path):
    project = _init_python_project(tmp_path)
    with_none = run_suite_on_dir("python", str(project), fail_fast=False)
    with_empty = run_suite_on_dir("python", str(project), fail_fast=False, external_gates=None)

    def _strip_timing(d):
        return {k: v for k, v in d.items() if k != "duration_ms"}

    assert [_strip_timing(r.to_dict()) for r in with_none] == [
        _strip_timing(r.to_dict()) for r in with_empty
    ]
