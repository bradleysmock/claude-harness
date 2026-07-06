"""Content-verification tests for commands/bisect.md (ticket 0015).

/bisect is a model-interpreted Markdown command that delegates execution to
bin/bisect-resolve.sh. Its runtime behavior is tested in test_0015_bisect_resolve.py;
these tests verify the command doc documents every behavior required by
requirements.md FR-1..FR-12 and NFR-1..NFR-3 so the model executes the right steps.

Limitation: these tests verify the instructions exist, not that the model executes
them at runtime.
"""
from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent.parent / "commands" / "bisect.md"


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def test_command_file_exists() -> None:
    assert DOC.exists(), "commands/bisect.md must exist"


def test_delegates_to_private_script() -> None:
    content = _content()
    assert "bin/bisect-resolve.sh" in content, "must delegate to bin/bisect-resolve.sh"
    assert "private implementation detail" in content.lower(), \
        "must document the script as a private implementation detail"


def test_argument_contract() -> None:
    content = _content()
    assert "--good" in content and "required" in content.lower(), "--good must be documented as required"
    assert "--bad" in content, "--bad must be documented"
    assert "default `HEAD`" in content or "default HEAD" in content, "--bad default HEAD must be documented"
    assert "--run" in content, "--run must be documented"


def test_ticket_validation_before_bisect() -> None:
    content = _content()
    assert "^[0-9]{4}$" in content, "must document the ^[0-9]{4}$ ticket validation pattern"
    lower = content.lower()
    assert "before bisect" in lower or "before starting bisect" in lower, \
        "must document erroring before bisect on an invalid boundary"


def test_subject_anchored_merge_resolution() -> None:
    content = _content()
    assert "--merges" in content, "must document scanning merge commits"
    assert r"ticket/XXXX-" in content, "must document the subject-anchored ticket pattern"
    lower = content.lower()
    assert "subject" in lower, "must document anchoring to the subject line"
    assert "body" in lower, "must document the body-mention false-positive guard"
    assert "no merge commit" in lower, "must document the no-merge-commit error"


def test_test_command_precedence() -> None:
    content = _content()
    lower = content.lower()
    assert "--run" in content
    assert ".claude/settings.json" in content and "test_command" in content
    assert "package.json" in content and "npm test" in content
    assert "[tool.pytest.ini_options]" in content or "[tool.pytest]" in content
    assert "pytest" in content
    assert "without" in lower and "does" in lower, \
        "must document that pyproject without a pytest section does not select pytest"


def test_multiword_wrapping() -> None:
    content = _content()
    lower = content.lower()
    assert "mktemp" in lower or "temporary script" in lower, "must document mktemp wrapping"
    assert "single-word" in lower or "single word" in lower, "must document single-word direct pass"
    assert "whitespace" in lower or "multi-word" in lower


def test_auto_good_bad_from_exit_code() -> None:
    content = _content()
    assert "git bisect run" in content, "must document git bisect run"
    lower = content.lower()
    assert "exit code" in lower or "exit-code" in lower or "exit codes" in lower
    assert "0" in content and "non-zero" in lower, "must document 0=good / non-zero=bad"


def test_reports_culprit_sha() -> None:
    content = _content()
    assert "first-bad" in content.lower() or "culprit" in content.lower()
    assert "<sha>" in content, "must document reporting the culprit SHA"


def test_ancestry_attribution_primary() -> None:
    content = _content()
    assert "--ancestry-path" in content, "must document ancestry-path traversal"
    lower = content.lower()
    assert "merge-commit ancestry" in lower or "merge commit ancestry" in lower
    assert "supplementary" in lower, "branch containment must be documented as supplementary only"
    assert "branch" in lower and "contains" in lower, "must mention branch containment as the supplementary mechanism"


def test_output_contract_em_dash_and_fallbacks() -> None:
    content = _content()
    assert "—" in content, "output contract must use a UTF-8 em-dash (U+2014)"
    assert "Regression introduced in commit" in content
    assert "part of ticket" in content
    assert "not linked to a ticket" in content
    lower = content.lower()
    assert "title:" in content, "must document the status.md title: source"
    assert "bare ticket number" in lower or "bare number" in lower, "must document the no-title fallback"


def test_cleanup_trap_single_path() -> None:
    content = _content()
    assert "trap 'git bisect reset || true' EXIT" in content, "must document the single trap-based reset"
    lower = content.lower()
    assert "sole" in lower or "only" in lower, "must document the trap as the sole cleanup path"
    assert "we are not bisecting" in lower, "must document avoiding the double-fire message"
    assert "success" in lower and "error" in lower, "must document firing on success and error paths"


def test_nfr_argument_lists_and_graceful_degradation() -> None:
    content = _content()
    lower = content.lower()
    assert "argument list" in lower, "must state shell commands use argument lists (NFR-2)"
    assert "string interpolation" in lower, "must state no string interpolation (NFR-2)"
    assert "no ticket merge commits" in lower, "must document graceful degradation (NFR-3)"
