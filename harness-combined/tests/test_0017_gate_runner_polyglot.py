"""Ticket 0017 — gate_run_on_dir polyglot aggregation, overrides, fail-closed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import server  # noqa: E402 - after importorskip guard
from models import GateError, GateResult, StackName  # noqa: E402


def _standards(tmp_path: Path, body: str) -> None:
    tickets = tmp_path / ".tickets"
    tickets.mkdir(exist_ok=True)
    (tickets / "_standards.md").write_text(body, encoding="utf-8")


def test_single_explicit_language_backcompat_shape(monkeypatch, tmp_path: Path) -> None:
    # FR-8: an explicit single language yields the exact pre-polyglot shape.
    monkeypatch.setattr(
        server, "run_suite_on_dir",
        lambda stack, directory, **kw: [GateResult("lint", True, [], 1)],
    )
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path)))
    assert out == {"passed": True, "language": "python"}


def test_no_override_does_not_pass_overrides_kwarg(monkeypatch, tmp_path: Path) -> None:
    # A suite stand-in WITHOUT an overrides parameter must keep working.
    def fake(stack, directory, fail_fast=True, *, standards_path=None,
             base_ref="main", config=None):
        return [GateResult("lint", True, [], 1)]

    monkeypatch.setattr(server, "run_suite_on_dir", fake)
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path)))
    assert out["passed"] is True


def test_polyglot_failure_aggregates(monkeypatch, tmp_path: Path) -> None:
    # FR-2 + FR-4: every detected stack runs; a fail in any language fails the run.
    monkeypatch.setattr(server, "_detect_stacks",
                        lambda d: [StackName.PYTHON, StackName.TYPESCRIPT])

    def fake(stack, directory, **kw):
        if str(stack) == "python":
            return [GateResult("lint", True, [], 1)]
        return [GateResult("lint", False,
                           [GateError("x", "f.ts", 1, 1, "E1", "error")], 1)]

    monkeypatch.setattr(server, "run_suite_on_dir", fake)
    out = json.loads(
        server.gate_run_on_dir(str(tmp_path), "auto", str(tmp_path), fail_fast=False)
    )
    assert out["passed"] is False
    assert out["languages"] == ["python", "typescript"]
    assert "findings_md" in out
    assert {g["language"] for g in out["gates"]} == {"python", "typescript"}


def test_polyglot_pass_includes_findings_md(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(server, "_detect_stacks",
                        lambda d: [StackName.PYTHON, StackName.TYPESCRIPT])
    monkeypatch.setattr(
        server, "run_suite_on_dir",
        lambda stack, directory, **kw: [GateResult("lint", True, [], 1)],
    )
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "auto", str(tmp_path)))
    assert out["passed"] is True
    assert out["languages"] == ["python", "typescript"]
    assert "**Languages detected**: python, typescript" in out["findings_md"]


def test_malformed_gates_block_fails_closed(monkeypatch, tmp_path: Path) -> None:
    # A malformed override must fail closed and NOT fall back to default gates.
    _standards(tmp_path, '```gates\npython.lint = "../evil check"\n```\n')
    called: list[int] = []

    def fake(*a, **k):
        called.append(1)
        return [GateResult("lint", True, [], 1)]

    monkeypatch.setattr(server, "run_suite_on_dir", fake)
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "auto", str(tmp_path)))
    assert out["passed"] is False
    assert out["gates"][0]["errors"][0]["code"] == "CONFIG_ERROR"
    assert called == []  # no fallback to default commands


def test_override_forwarded_to_suite(monkeypatch, tmp_path: Path) -> None:
    # FR-5: a valid override reaches the language suite as an argv list.
    _standards(tmp_path, '```gates\npython.lint = "ruff check ."\n```\n')
    captured: dict = {}

    def fake(stack, directory, **kw):
        captured.update(kw)
        return [GateResult("lint", True, [], 1)]

    monkeypatch.setattr(server, "run_suite_on_dir", fake)
    server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path))
    assert captured.get("overrides") == {"lint": ["ruff", "check", "."]}
