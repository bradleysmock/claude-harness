"""Ticket 0017 — _format_polyglot_findings heading/format contract (FR-3, FR-8)."""
from __future__ import annotations

import pytest

pytest.importorskip("mcp")

from models import GateError, GateResult, LanguageResult, StackName  # noqa: E402
from server import _format_polyglot_findings  # noqa: E402


def _pass(gate: str) -> GateResult:
    return GateResult(gate=gate, passed=True, errors=[], duration_ms=3)


def _fail(gate: str) -> GateResult:
    return GateResult(
        gate=gate, passed=False,
        errors=[GateError("bad thing", "impl.py", 7, 2, "E1", "error")],
        duration_ms=5,
    )


def test_multi_language_headings_and_header() -> None:
    out = _format_polyglot_findings(
        [
            LanguageResult(StackName.PYTHON, [_pass("lint")]),
            LanguageResult(StackName.TYPESCRIPT, [_fail("lint")]),
        ],
        "/wt",
    )
    assert "**Languages detected**: python, typescript" in out
    assert "## python / lint" in out
    assert "## typescript / lint" in out


def test_single_language_has_no_plural_header_or_prefix() -> None:
    out = _format_polyglot_findings(
        [LanguageResult(StackName.PYTHON, [_pass("lint"), _pass("test")])],
        "/wt",
    )
    assert "**Languages detected**" not in out
    assert "## lint" in out
    assert "## python / lint" not in out


def test_failing_error_lines_are_rendered() -> None:
    out = _format_polyglot_findings(
        [LanguageResult(StackName.PYTHON, [_fail("lint")])], "/wt"
    )
    assert "- `impl.py:7` [`E1`]: bad thing" in out
    assert "**Status**: FAIL" in out


def test_passing_gate_renders_clean() -> None:
    out = _format_polyglot_findings(
        [LanguageResult(StackName.PYTHON, [_pass("lint")])], "/wt"
    )
    assert "**Status**: PASS" in out
    assert "clean" in out
