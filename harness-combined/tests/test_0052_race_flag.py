"""FR-1: the Stop hook's Go test command includes -race, matching the MCP gate.

gates_go() builds its commands through run_gate(); we monkeypatch run_gate to
capture the argument lists it is asked to run and assert the Go test invocation
carries -race (and that gofmt / go vet are unchanged).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HOOKS = Path(__file__).parent.parent / "hooks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("stop_full_gate")


def _captured_go_commands(monkeypatch, tmp_path: Path) -> list[list[str]]:
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run_gate(executable, args, cwd):
        calls.append([executable, *args])
        return 0, ""

    monkeypatch.setattr(gate, "run_gate", fake_run_gate)
    gate.gates_go(tmp_path)
    return calls


def test_go_test_command_includes_race(monkeypatch, tmp_path):
    calls = _captured_go_commands(monkeypatch, tmp_path)
    go_test = [c for c in calls if c[:2] == ["go", "test"]]
    assert go_test, "gates_go must run `go test`"
    assert "-race" in go_test[0], f"Go test command must include -race, got {go_test[0]}"


def test_race_matches_mcp_gate_source(monkeypatch, tmp_path):
    # Parity anchor: the MCP Go gate also runs the race detector.
    mcp_go = (Path(__file__).parent.parent / "gates" / "go.py").read_text(encoding="utf-8")
    assert "-race" in mcp_go, "gates/go.py (MCP gate) must run go test with -race"
    calls = _captured_go_commands(monkeypatch, tmp_path)
    assert any(c[:2] == ["go", "test"] and "-race" in c for c in calls)


def test_gofmt_and_vet_unchanged(monkeypatch, tmp_path):
    calls = _captured_go_commands(monkeypatch, tmp_path)
    assert ["gofmt", "-l", "."] in calls, "gofmt argument list must be unchanged"
    assert ["go", "vet", "./..."] in calls, "go vet argument list must be unchanged"
