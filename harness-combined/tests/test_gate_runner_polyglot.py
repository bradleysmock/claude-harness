"""Regression guards for the polyglot gate runner (ticket 0007).

These pin the invariants that previously produced false gate failures on a
polyglot repo: silent/empty failures, wrong project-root resolution, and a
single-language collapse on auto-detect.
"""
from __future__ import annotations

from pathlib import Path

from gates import append_tool_error_if_silent, find_config_root
from gates.typescript import _changed_test_files
from models import GateError
from server import _detect_stacks


def _finding() -> GateError:
    return GateError(message="real", file="f.ts", line=1, column=1, code="E1", severity="error")


# ── FR-3: no silent / empty failures ──────────────────────────────────────────

def test_nonzero_exit_with_no_findings_yields_one_tool_error() -> None:
    errors: list[GateError] = []
    append_tool_error_if_silent(errors, returncode=2, output="cannot find module")
    assert [e.code for e in errors] == ["TOOL_ERROR"]


def test_success_exit_is_a_noop() -> None:
    errors: list[GateError] = []
    append_tool_error_if_silent(errors, returncode=0, output="")
    assert errors == []


def test_real_findings_are_never_masked_by_tool_error() -> None:
    errors = [_finding()]
    append_tool_error_if_silent(errors, returncode=1, output="boom")
    assert [e.code for e in errors] == ["E1"]


def test_bandit_style_success_code_one_is_not_a_tool_error() -> None:
    errors: list[GateError] = []
    append_tool_error_if_silent(errors, returncode=1, output="", success_codes=(0, 1))
    assert errors == []


# ── FR-2: per-tool project-root resolution ────────────────────────────────────

def test_find_config_root_same_directory(tmp_path: Path) -> None:
    (tmp_path / "tsconfig.json").write_text("{}")
    assert find_config_root(tmp_path, ("tsconfig.json",)) == tmp_path


def test_find_config_root_one_level_down(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "tsconfig.json").write_text("{}")
    assert find_config_root(tmp_path, ("tsconfig.json",)) == web


def test_find_config_root_ignores_vendored_dirs(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "tsconfig.json").write_text("{}")
    assert find_config_root(tmp_path, ("tsconfig.json",)) == tmp_path


def test_find_config_root_falls_back_to_directory(tmp_path: Path) -> None:
    assert find_config_root(tmp_path, ("tsconfig.json",)) == tmp_path


# ── FR-7: auto-detect never collapses a polyglot repo to one stack ─────────────

def test_detect_stacks_reports_every_present_stack(tmp_path: Path) -> None:
    # FR-1: detection is manifest-only — a Python descriptor, not a bare *.py file.
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pyproject.toml").write_text("")
    stacks = _detect_stacks(str(tmp_path))
    assert "typescript" in stacks
    assert "python" in stacks


def test_detect_stacks_finds_subdir_markers(tmp_path: Path) -> None:
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "tsconfig.json").write_text("{}")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "Cargo.toml").write_text("")
    (tmp_path / "pyproject.toml").write_text("")  # FR-1: manifest, not a raw .py
    assert {"rust", "typescript", "python"}.issubset(set(_detect_stacks(str(tmp_path))))


# ── FR-4: jest scoping fails closed ───────────────────────────────────────────

def test_changed_test_files_returns_none_outside_a_repo(tmp_path: Path) -> None:
    # No git history to diff against → None, which callers treat as
    # "run the full suite", never as "skip all".
    assert _changed_test_files(tmp_path) is None
