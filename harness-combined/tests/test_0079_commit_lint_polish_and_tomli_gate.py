"""Ticket 0079: `polish` commit-lint type + tomli/mypy gate fix.

`build-ticket.md` Step 7b.5 mandates `polish: craft round N` commits for an
accepted craft-polish round; `commit_lint.py`'s default types never
included it. Separately, `panel_detect.py`'s tomllib/tomli fallback used a
runtime `try/except` mypy can't reason about without `tomli` installed —
moved to a `sys.version_info` guard, the one form mypy statically narrows.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from gates.commit_lint import (
    DEFAULT_ALLOWED_TYPES,
    CommitLintConfig,
    _compile_subject_pattern,
    run,
)

_ROOT = Path(__file__).resolve().parent.parent


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _commit(repo: Path, subject: str) -> None:
    (repo / "f.txt").write_text(subject, encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", subject)


def _matches(subject: str) -> bool:
    pattern = _compile_subject_pattern(CommitLintConfig())
    return pattern.match(subject) is not None


def test_polish_is_an_allowed_type() -> None:
    assert "polish" in DEFAULT_ALLOWED_TYPES


def test_polish_craft_round_subject_matches() -> None:
    assert _matches("polish: craft round 1")


def test_unknown_type_still_rejected() -> None:
    assert not _matches("wip: still not allowed")


def test_polish_commit_passes_end_to_end(tmp_path: Path) -> None:
    """Exercises the acceptance criterion as literally stated: `commit_lint`'s
    public `run()` entry point, not just the pattern helper."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    _commit(repo, "chore: initial commit")
    _git(repo, "checkout", "-b", "feature")
    _commit(repo, "polish: craft round 1")
    result = run("feature", str(repo))
    assert result.passed is True
    assert result.errors == []


def test_no_existing_type_removed() -> None:
    for existing in ("feat", "fix", "docs", "style", "refactor", "perf", "test", "chore", "build", "ci", "revert"):
        assert existing in DEFAULT_ALLOWED_TYPES


def test_panel_detect_tomllib_name_is_usable() -> None:
    import panel_detect

    assert hasattr(panel_detect.tomllib, "loads")


def test_panel_detect_mypy_clean_without_tomli() -> None:
    """Regression for the actual defect: mypy must resolve the import
    without `tomli` installed (it's intentionally absent on this
    interpreter — see requirements.txt's python_version marker)."""
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "panel_detect.py"],
        cwd=_ROOT, capture_output=True, text=True,
    )
    assert "tomli" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout
