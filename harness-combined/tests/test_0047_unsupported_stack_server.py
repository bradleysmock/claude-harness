"""Ticket 0047 — honest unsupported-stack handling in server.py auto mode.

Covers FR-1 (explicit unsupported-stack error instead of a Python default),
FR-5 (bare-Python fallback / _detect_language removed), and regression guards for
the already-delivered FR-2 (go.mod one-level parity) and FR-3 server-side
vendored exclusions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import server  # noqa: E402 - after importorskip guard
from models import GateResult, StackName  # noqa: E402


def test_java_only_dir_returns_unsupported_error(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>\n")
    (tmp_path / "Main.java").write_text("class Main {}\n")
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "auto", str(tmp_path)))
    assert out["passed"] is False
    assert out["unsupported_stack"] is True
    assert out["directory"] == str(tmp_path)
    assert "pom.xml" in out["markers_found"]
    # It must NOT masquerade as a Python gate result.
    assert out.get("language") != "python"
    assert "gates" not in out


def test_empty_dir_returns_unsupported_error(tmp_path: Path) -> None:
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "auto", str(tmp_path)))
    assert out["passed"] is False
    assert out["unsupported_stack"] is True
    assert out["markers_found"] == []


def test_unsupported_error_names_remediation(tmp_path: Path) -> None:
    payload = server._unsupported_stack_payload(str(tmp_path))
    msg = payload["error"].lower()
    assert str(tmp_path) in payload["error"]
    assert "explicit language" in msg
    assert "add gate" in msg


def test_unsupported_markers_scanned_one_level_only(tmp_path: Path) -> None:
    # A marker two levels down is not reported (bounded scan, NFR-1).
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "pom.xml").write_text("<project/>\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "Gemfile").write_text("source 'x'\n")
    payload = server._unsupported_stack_payload(str(tmp_path))
    assert "Gemfile" in payload["markers_found"]  # one level down
    assert "pom.xml" not in payload["markers_found"]  # two levels down


def test_go_mod_one_level_down_detected(tmp_path: Path) -> None:
    # FR-2 parity regression guard (delivered by 0017's _scan_roots).
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "go.mod").write_text("module x\n")
    assert StackName.GO in server._detect_stacks(str(tmp_path))


def test_node_modules_only_py_not_detected_as_python(tmp_path: Path) -> None:
    # FR-3 server-side regression guard: vendored .py must not trigger Python.
    (tmp_path / "package.json").write_text("{}\n")
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "shim.py").write_text("x = 1\n")
    stacks = server._detect_stacks(str(tmp_path))
    assert StackName.PYTHON not in stacks
    assert StackName.TYPESCRIPT in stacks


def test_detect_language_removed(tmp_path: Path) -> None:
    # FR-5: the bare-Python fallback function is gone.
    assert not hasattr(server, "_detect_language")


def test_explicit_language_dispatch_preserved(monkeypatch, tmp_path: Path) -> None:
    # FR-5: explicit-language callers still dispatch to the suite, unchanged —
    # they never reach the unsupported-stack branch even with no manifest present.
    dispatched: list[str] = []

    def fake(stack, directory, **kwargs):
        dispatched.append(str(stack))
        return [GateResult(gate="lint", passed=True, errors=[], duration_ms=1)]

    monkeypatch.setattr(server, "run_suite_on_dir", fake)
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path)))
    assert dispatched == ["python"]
    assert out["passed"] is True
    assert "unsupported_stack" not in out
