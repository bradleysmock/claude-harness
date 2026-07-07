"""FR-3: pre_write_guard honors a suppression marker only with a reason suffix.

Bare markers no longer bypass the guard and are themselves blocking violations;
reasoned markers pass and still suppress the co-located forbidden-shape check.
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


guard = _load("pre_write_guard")


def _rule_ids(content: str, path: str = "m.py") -> list[str]:
    return [v.rule_id for v in guard.find_violations(path, content)]


def test_bare_nosec_is_blocked() -> None:
    ids = _rule_ids("x = 1  # nosec")
    assert "suppression:bare-marker" in ids


def test_reasoned_nosec_is_allowed() -> None:
    ids = _rule_ids("x = 1  # nosec: fixture uses literal creds")
    assert "suppression:bare-marker" not in ids


def test_bare_nosec_no_longer_bypasses_shell_true() -> None:
    ids = _rule_ids("run(cmd, shell=True)  # nosec")
    assert "py:shell-true" in ids  # bare marker no longer counts as justification
    assert "suppression:bare-marker" in ids


def test_reasoned_nosec_still_suppresses_shell_true() -> None:
    ids = _rule_ids("run(cmd, shell=True)  # nosec: subprocess needs a shell here")
    assert ids == []


def test_bare_noqa_is_blocked_reasoned_allowed() -> None:
    assert "suppression:bare-marker" in _rule_ids("x = 1  # noqa")
    assert "suppression:bare-marker" not in _rule_ids("x = 1  # noqa: E501 long url")


def test_multi_marker_line_reports_each_bare_marker() -> None:
    markers = guard.bare_markers("x = 1  # noqa  # nosec")
    assert "# noqa" in markers
    assert "nosec" in markers


def test_bare_cast_marker_blocked_reasoned_allowed() -> None:
    assert guard.bare_markers("v = raw  // cast:") == ["// cast:"]
    assert guard.bare_markers("v = raw  // cast: json boundary") == []


def test_marker_is_reasoned_helper() -> None:
    assert guard.marker_is_reasoned("a  # nosec: why", "nosec") is True
    assert guard.marker_is_reasoned("a  # nosec", "nosec") is False
    assert guard.marker_is_reasoned("a  # clean", "nosec") is False


def test_bare_marker_in_prose_docs_is_not_blocked() -> None:
    # A docs/rule file (no detected language) must be able to *discuss* a bare
    # suppression token without the write being blocked — prose has no
    # reason-suffix escape hatch (NFR-3). Mirrors context/rules/javascript.md,
    # which literally contains "Never bare `eslint-disable`."
    doc = "Never bare `eslint-disable`.\nAvoid a lone `# noqa` in examples."
    assert "suppression:bare-marker" not in _rule_ids(doc, path="rules/javascript.md")
    assert _rule_ids(doc, path="notes.txt") == []


def test_bare_marker_still_blocked_in_source_files() -> None:
    # The escape hatch is prose-only: recognized source files still enforce FR-3.
    assert "suppression:bare-marker" in _rule_ids("x = 1  # noqa", path="m.py")
    assert "suppression:bare-marker" in _rule_ids("const x = 1 // eslint-disable", path="m.ts")
