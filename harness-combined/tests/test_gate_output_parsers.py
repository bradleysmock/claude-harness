"""Regression test: `_parse_mypy_output` must handle `--show-column-numbers`.

Pre-existing bug, unrelated to tickets 0074-0077: the gate's own mypy
invocation passes `--show-column-numbers`, but the parsing regex only matched
the columnless `file:line: severity:` form, so every real error fell through
to the generic TOOL_ERROR fallback instead of a structured finding.
"""
from __future__ import annotations

from gates.python import _parse_bandit_json, _parse_mypy_output, _security_gate_dir


def test_parses_error_with_column_number():
    output = 'm.py:9:41: error: Cannot find implementation or library stub for module named "x"  [import-not-found]\n'
    errors = _parse_mypy_output(output)
    assert len(errors) == 1
    assert errors[0].file == "m.py"
    assert errors[0].line == 9
    assert errors[0].column == 41
    assert errors[0].code == "import-not-found"
    assert errors[0].severity == "error"


def test_still_parses_error_without_column_number():
    output = "m.py:9: error: some legacy-format message  [misc]\n"
    errors = _parse_mypy_output(output)
    assert len(errors) == 1
    assert errors[0].column is None
    assert errors[0].line == 9


def test_note_lines_are_skipped():
    output = (
        'm.py:9:41: error: real error  [arg-type]\n'
        'm.py:9:41: note: some hint\n'
    )
    errors = _parse_mypy_output(output)
    assert len(errors) == 1
    assert errors[0].severity == "error"


def test_bandit_json_parses_real_findings():
    """Regression: without `-q`, bandit prints a progress bar ahead of the JSON
    body, which silently degrades to zero parsed findings (pre-existing bug)."""
    payload = (
        '{"results": [{"filename": "m.py", "test_name": "hardcoded_sql",'
        ' "issue_text": "possible SQL injection", "line_number": 3,'
        ' "test_id": "B608"}], "errors": []}'
    )
    errors = _parse_bandit_json(payload)
    assert len(errors) == 1
    assert errors[0].code == "B608"
    assert errors[0].line == 3


def test_bandit_cmd_includes_quiet_flag():
    """`-q` must be present so a progress bar never pollutes stdout JSON."""
    import gates.python as pymod

    captured: dict[str, list[str]] = {}

    def _fake_exec_dir(cmd, directory, timeout=60):
        captured["cmd"] = cmd
        return pymod.ProcessResult("{\"results\": [], \"errors\": []}", "", 0)

    original = pymod._exec_dir
    pymod._exec_dir = _fake_exec_dir
    try:
        _security_gate_dir(".")
    finally:
        pymod._exec_dir = original
    assert "-q" in captured["cmd"]
