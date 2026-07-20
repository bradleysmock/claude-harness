"""Ticket 0065 — gate_run_red_check MCP tool: wraps check_red()/next_action(),
containing any exception from either as tool_error/escalate_skip."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import server  # noqa: E402 - after importorskip guard


def test_proceeds_on_red(tmp_path: Path) -> None:
    (tmp_path / "test_thing.py").write_text(
        "def test_target():\n    assert False\n", encoding="utf-8",
    )
    out = json.loads(server.gate_run_red_check(
        str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"],
        attempt=1, max_attempts=3,
    ))
    assert out["classification"] == "red"
    assert out["action"] == "proceed"


def test_blocking_retries_then_escalates(tmp_path: Path) -> None:
    (tmp_path / "test_thing.py").write_text(
        "def test_target():\n    assert True\n", encoding="utf-8",
    )
    node_ids = ["test_thing.py::test_target"]
    early = json.loads(server.gate_run_red_check(
        str(tmp_path), "python", "test_thing.py", node_ids, attempt=1, max_attempts=3,
    ))
    assert early["classification"] == "blocking"
    assert early["action"] == "retry"

    exhausted = json.loads(server.gate_run_red_check(
        str(tmp_path), "python", "test_thing.py", node_ids, attempt=3, max_attempts=3,
    ))
    assert exhausted["classification"] == "blocking"
    assert exhausted["action"] == "escalate_skip"


def test_caller_error_is_contained_as_tool_error(tmp_path: Path) -> None:
    out = json.loads(server.gate_run_red_check(
        str(tmp_path), "cobol", "test_thing.py", ["x"], attempt=1, max_attempts=3,
    ))
    assert out["classification"] == "tool_error"
    assert out["action"] == "escalate_skip"


def test_tool_error_never_consumes_a_retry(tmp_path: Path) -> None:
    out = json.loads(server.gate_run_red_check(
        str(tmp_path), "cobol", "test_thing.py", ["x"], attempt=1, max_attempts=1,
    ))
    assert out["action"] == "escalate_skip"


def test_generic_exception_from_check_red_is_contained_as_tool_error(
    tmp_path: Path, monkeypatch,
) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(server, "check_red", _raise)
    out = json.loads(server.gate_run_red_check(
        str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"],
        attempt=1, max_attempts=3,
    ))
    assert out["classification"] == "tool_error"
    assert out["action"] == "escalate_skip"
