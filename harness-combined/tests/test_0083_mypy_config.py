# harness-combined/tests/test_0083_mypy_config.py
"""Ticket 0083 — the mypy configuration that clears three import-resolution errors.

`hooks/` on `mypy_path`, a `types-PyYAML` requirement, and one narrowly scoped
`sarif` override are the whole fix for the `_common`, `yaml`, and `sarif` import
errors; these tests pin the config so a later edit cannot quietly reintroduce the
debt (or widen the one permitted suppression into a blanket ignore).
"""
from __future__ import annotations

import sys
from pathlib import Path

# tomllib is stdlib on Python >= 3.11; tomli is the 3.10 backport. Same
# `sys.version_info` guard panel_detect.py uses, for the same reason: mypy
# narrows on this exact form and never tries to resolve `tomli` on 3.11+.
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_REPO_ROOT = Path(__file__).parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_REQUIREMENTS = _REPO_ROOT / "requirements.txt"


def _mypy_config() -> dict[str, object]:
    with _PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    tool_tables = data["tool"]
    assert isinstance(tool_tables, dict)
    mypy_settings = tool_tables["mypy"]
    assert isinstance(mypy_settings, dict)
    return mypy_settings


def test_mypy_path_includes_hooks() -> None:
    # FR-1: both hooks import a `_common` sibling that mypy cannot see at all
    # unless `hooks` is a search root — the same root cause as the `tests` entry.
    mypy_search_path = _mypy_config()["mypy_path"]
    assert isinstance(mypy_search_path, str)
    assert "hooks" in mypy_search_path.split(":")


def test_mypy_path_keeps_its_existing_roots() -> None:
    # The `hooks` entry is appended, not a rewrite: `.` and `tests` still resolve.
    mypy_search_path = _mypy_config()["mypy_path"]
    assert isinstance(mypy_search_path, str)
    roots = mypy_search_path.split(":")
    assert roots[:2] == [".", "tests"]


def test_sarif_is_the_only_mypy_override() -> None:
    # FR-3 / AC-3: `sarif-tools` has no stub package in existence, so a scoped
    # per-module override is the correct permanent fix — and the only one.
    overrides = _mypy_config()["overrides"]
    assert isinstance(overrides, list)
    assert len(overrides) == 1
    sarif_override = overrides[0]
    assert isinstance(sarif_override, dict)
    assert sarif_override["module"] == ["sarif"]
    assert sarif_override["ignore_missing_imports"] is True


def test_no_blanket_ignore_missing_imports() -> None:
    # NFR-1: the suppression stays scoped to the one stubless module; a
    # top-level `ignore_missing_imports` would silence every future import gap.
    assert "ignore_missing_imports" not in _mypy_config()


def test_types_pyyaml_is_a_declared_requirement() -> None:
    # FR-2: a real stub package exists for PyYAML, so it is installed rather
    # than suppressed.
    requirement_lines = _REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    types_pyyaml_declarations = [
        requirement_line
        for requirement_line in requirement_lines
        if requirement_line.strip().lower().startswith("types-pyyaml")
    ]
    assert len(types_pyyaml_declarations) == 1


def test_hooks_and_coverage_gate_carry_no_type_suppressions() -> None:
    # AC-4 / NFR-1: the config fix resolves these imports, so none of the three
    # files the errors pointed at needed a suppression of its own.
    for relative_path in (
        "hooks/pre_write_guard.py",
        "hooks/pre_ticket_diff.py",
        "gates/coverage.py",
    ):
        source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "type: ignore" not in source, relative_path
