"""Tests for the conventional-commit lint gate (ticket 0003).

Unit tests exercise the pure regex/config surface directly; integration tests
build a throwaway git repo under ``tmp_path`` and call ``run()`` end-to-end
(this is exactly how a standalone CI invocation would use the gate).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from gates.commit_lint import (
    DEFAULT_ALLOWED_TYPES,
    CommitLintConfig,
    _compile_subject_pattern,
    _parse_standards_config,
    _resolve_base_branch,
    run,
)


# ── Unit: subject pattern (FR-3, FR-6, FR-7, D-01) ───────────────────────────
def _matches(subject: str, config: CommitLintConfig | None = None) -> bool:
    pattern = _compile_subject_pattern(config or CommitLintConfig())
    return pattern.match(subject) is not None


@pytest.mark.parametrize("subject", [
    "feat(ui): add button",
    "fix: correct off-by-one",
    "chore(deps): bump lib",
    "revert: feat(ui): add button",
    "docs: explain the gate",
])
def test_valid_subjects_match(subject: str) -> None:
    assert _matches(subject)


@pytest.mark.parametrize("subject", [
    "wip: stuff",            # unknown type
    "fix",                   # no colon / subject
    "fix: ",                 # empty subject
    "",                      # empty message
    "feature: x",            # not an allowed type
    "feat(ui) add button",   # missing colon
])
def test_invalid_subjects_do_not_match(subject: str) -> None:
    assert not _matches(subject)


def test_default_types_cover_the_standard_set() -> None:
    for t in ("feat", "chore", "revert", "ci", "build"):
        assert _matches(f"{t}: something")
    assert not _matches("wip: something")  # not in defaults


def test_require_scope_enforces_parenthetical() -> None:
    scoped = CommitLintConfig(require_scope=True)
    assert not _matches("feat: add widget", scoped)
    assert _matches("feat(ui): add widget", scoped)
    # Default (optional scope) accepts both.
    assert _matches("feat: add widget")
    assert _matches("feat(ui): add widget")


def test_pattern_is_not_redos_prone() -> None:
    # D-01: an adversarial 200-char subject must match in well under 100ms.
    adversarial = "feat" + "(" * 50 + "x" * 150
    pattern = _compile_subject_pattern(CommitLintConfig())
    start = time.monotonic()
    for _ in range(200):
        pattern.match(adversarial[:200])
    assert (time.monotonic() - start) < 0.1


# ── Unit: _standards.md parsing (FR-9, D2-04) ────────────────────────────────
def test_parse_standards_allowed_types_override() -> None:
    text = "# Standards\n\n## Commit Lint\nallowed_types: [wip, feat]\n"
    overrides, warnings = _parse_standards_config(text)
    assert overrides["allowed_types"] == ("wip", "feat")
    assert warnings == []


def test_parse_standards_require_scope() -> None:
    overrides, warnings = _parse_standards_config("## Commit Lint\nrequire_scope: true\n")
    assert overrides["require_scope"] is True
    assert warnings == []


def test_parse_standards_empty_list_falls_back_with_warning() -> None:
    overrides, warnings = _parse_standards_config("## Commit Lint\nallowed_types: []\n")
    assert "allowed_types" not in overrides  # D2-04: empty is not a valid override
    assert len(warnings) == 1


def test_parse_standards_malformed_warns_and_defaults() -> None:
    overrides, warnings = _parse_standards_config("## Commit Lint\nallowed_types: feat, fix\n")
    assert "allowed_types" not in overrides
    assert len(warnings) == 1


def test_parse_standards_absent_section_is_noop() -> None:
    overrides, warnings = _parse_standards_config("# Standards\n\nNo commit lint here.\n")
    assert overrides == {} and warnings == []


# ── Integration: temp git repo helpers ───────────────────────────────────────
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=False,
    )


def _init_repo(repo: Path, default_branch: str = "main") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", default_branch)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit(repo: Path, subject: str, body: str = "") -> str:
    marker = repo / "f.txt"
    marker.write_text(subject + "\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    message = subject if not body else f"{subject}\n\n{body}"
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture()
def base_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "chore: initial commit")  # a base commit on main
    return repo


# ── Integration: run() (FR-2, FR-4, FR-5, D-04, D2-02) ───────────────────────
def test_all_valid_commits_pass(base_repo: Path) -> None:
    _git(base_repo, "checkout", "-b", "feature")
    _commit(base_repo, "feat(x): one")
    _commit(base_repo, "fix: two")
    result = run("feature", str(base_repo))
    assert result.passed is True
    assert result.errors == []
    assert result.gate == "commit_lint"


def test_one_invalid_commit_yields_one_error_with_short_sha(base_repo: Path) -> None:
    _git(base_repo, "checkout", "-b", "feature")
    _commit(base_repo, "feat(x): good one")
    bad_sha = _commit(base_repo, "wip: broken thing")
    _commit(base_repo, "fix: good two")
    result = run("feature", str(base_repo))
    assert result.passed is False
    errs = [e for e in result.errors if e.severity == "error"]
    assert len(errs) == 1
    assert errs[0].file == bad_sha[:7]           # FR-4: exact sha[:7]
    assert errs[0].message == f"{bad_sha[:7]}: wip: broken thing"  # NFR-3
    assert errs[0].code == "COMMIT_LINT"


def test_no_commits_ahead_passes(base_repo: Path) -> None:
    _git(base_repo, "checkout", "-b", "feature")  # no new commits
    result = run("feature", str(base_repo))
    assert result.passed is True
    assert result.errors == []


def test_multiline_body_only_subject_is_checked(base_repo: Path) -> None:
    _git(base_repo, "checkout", "-b", "feature")
    _commit(base_repo, "feat(x): subject ok", body="wip: this body line must be ignored\nmore text")
    result = run("feature", str(base_repo))
    assert result.passed is True


def test_merge_commit_is_excluded(base_repo: Path) -> None:
    _git(base_repo, "checkout", "-b", "side")
    _commit(base_repo, "feat(x): side work")
    _git(base_repo, "checkout", "main")
    _commit(base_repo, "fix: main work")
    # Create a real merge commit whose subject starts with "Merge".
    _git(base_repo, "checkout", "-b", "feature")
    _git(base_repo, "merge", "--no-ff", "side", "-m", "Merge branch 'side' into feature")
    result = run("feature", str(base_repo))
    assert result.passed is True  # the "Merge ..." subject is not flagged


def test_require_scope_flag_end_to_end(base_repo: Path) -> None:
    _git(base_repo, "checkout", "-b", "feature")
    _commit(base_repo, "feat: no scope here")
    passed_default = run("feature", str(base_repo))
    assert passed_default.passed is True
    strict = run("feature", str(base_repo), CommitLintConfig(require_scope=True))
    assert strict.passed is False


def test_injection_branch_name_is_rejected(base_repo: Path) -> None:
    # D-04 adv: a branch name that looks like a git option must fail closed.
    result = run("--format=injected", str(base_repo))
    assert result.passed is False
    assert result.errors[0].code == "INVALID_BRANCH"


def test_nonexistent_branch_yields_git_error(base_repo: Path) -> None:
    # D2-02: syntactically valid but missing branch → GIT_ERROR (fail closed).
    result = run("does-not-exist", str(base_repo))
    assert result.passed is False
    assert any(e.code == "GIT_ERROR" for e in result.errors)


def test_unknown_base_branch_fails_closed(tmp_path: Path) -> None:
    # D-02: no `main`, no origin/HEAD → BASE_BRANCH_UNKNOWN, never a false pass.
    repo = tmp_path / "trunkrepo"
    _init_repo(repo, default_branch="trunk")
    _commit(repo, "feat(x): only commit")
    result = run("trunk", str(repo))
    assert result.passed is False
    assert result.errors[0].code == "BASE_BRANCH_UNKNOWN"


def test_base_falls_back_to_origin_head(tmp_path: Path) -> None:
    # When `main` is absent but a valid origin/HEAD points at the real default,
    # resolution uses the sanitised fallback rather than failing.
    repo = tmp_path / "fallback"
    _init_repo(repo, default_branch="mainline")
    _commit(repo, "chore: base")
    # Simulate a remote default pointer to an existing local branch.
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/mainline")
    _git(repo, "update-ref", "refs/remotes/origin/mainline", "HEAD")
    base, error = _resolve_base_branch(CommitLintConfig(), str(repo))
    assert error is None
    assert base == "mainline"


def test_standards_override_allows_custom_type(base_repo: Path) -> None:
    # FR-9 happy path end-to-end: _standards.md widens the allowed set.
    tickets = base_repo / ".tickets"
    tickets.mkdir()
    (tickets / "_standards.md").write_text(
        "# Standards\n\n## Commit Lint\nallowed_types: [wip, feat]\n", encoding="utf-8",
    )
    _git(base_repo, "checkout", "-b", "feature")
    _commit(base_repo, "wip: normally invalid")
    result = run("feature", str(base_repo))
    assert result.passed is True


def test_standards_empty_list_still_uses_defaults(base_repo: Path) -> None:
    # D2-04 end-to-end: empty override → defaults + warning, still lints normally.
    tickets = base_repo / ".tickets"
    tickets.mkdir()
    (tickets / "_standards.md").write_text("## Commit Lint\nallowed_types: []\n", encoding="utf-8")
    _git(base_repo, "checkout", "-b", "feature")
    _commit(base_repo, "feat(x): still valid under defaults")
    result = run("feature", str(base_repo))
    assert result.passed is True
    assert any(e.severity == "warning" for e in result.errors)


def test_default_allowed_types_is_the_conventional_set() -> None:
    assert set(DEFAULT_ALLOWED_TYPES) >= {"feat", "fix", "docs", "chore", "revert", "ci", "build"}


# ── Fail-closed on git timeout / missing binary (M1) ─────────────────────────
def test_git_timeout_during_resolution_fails_closed(base_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(args: list[str], project_root: str) -> object:
        raise subprocess.TimeoutExpired(cmd=["git", *args], timeout=5)

    monkeypatch.setattr("gates.commit_lint._run_git", boom)
    result = run("feature", str(base_repo))
    assert result.passed is False
    assert any(e.code == "GIT_ERROR" for e in result.errors)
    # No path/command is echoed — only the failure class.
    assert all("/" not in (e.message or "") or "failing closed" in (e.message or "") for e in result.errors)


@pytest.mark.parametrize("exc", [FileNotFoundError("git"), PermissionError("git not executable")])
def test_unspawnable_git_fails_closed(base_repo: Path, monkeypatch: pytest.MonkeyPatch, exc: OSError) -> None:
    def boom(args: list[str], project_root: str) -> object:
        raise exc

    monkeypatch.setattr("gates.commit_lint._run_git", boom)
    result = run("feature", str(base_repo))
    assert result.passed is False
    assert any(e.code == "GIT_ERROR" for e in result.errors)


# ── Leading-dash ref rejection (m1) ──────────────────────────────────────────
@pytest.mark.parametrize("bad", ["-n", "--all", "--format=%H"])
def test_leading_dash_branch_rejected(base_repo: Path, bad: str) -> None:
    result = run(bad, str(base_repo))
    assert result.passed is False
    assert result.errors[0].code == "INVALID_BRANCH"


def test_non_merge_commit_named_merge_is_skipped(base_repo: Path) -> None:
    # A *regular* commit whose subject starts with "Merge " is not a merge commit,
    # so `--no-merges` keeps it; the _MERGE_RE guard is what skips it (o1/o2).
    _git(base_repo, "checkout", "-b", "feature")
    _commit(base_repo, "Merge notes from meeting")  # not conventional, not a merge
    result = run("feature", str(base_repo))
    assert result.passed is True  # skipped by the merge-subject guard, not flagged


# ── Server MCP tool wrapper (m2 / FR-1) ──────────────────────────────────────
def test_server_tool_returns_gate_json(base_repo: Path) -> None:
    import json
    pytest.importorskip("mcp")
    import server

    _git(base_repo, "checkout", "-b", "feature")
    _commit(base_repo, "feat(x): ok")
    payload = json.loads(server.commit_lint("feature", str(base_repo)))
    assert payload["gate"] == "commit_lint"
    assert payload["passed"] is True
    assert payload["errors"] == []


def test_server_tool_invalid_branch_json(base_repo: Path) -> None:
    import json
    pytest.importorskip("mcp")
    import server

    payload = json.loads(server.commit_lint("--format=x", str(base_repo)))
    assert payload["passed"] is False
    assert payload["errors"][0]["code"] == "INVALID_BRANCH"


def test_server_tool_handles_subprocess_error(base_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    pytest.importorskip("mcp")
    import server

    def boom(branch: str, project_root: str, config: object) -> object:
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=5)

    monkeypatch.setattr(server, "run_commit_lint", boom)
    payload = json.loads(server.commit_lint("feature", str(base_repo)))
    assert "error" in payload  # returns structured error, does not raise


# ── FR-8: deliver flow wires the gate in ─────────────────────────────────────
def test_deliver_flow_invokes_commit_lint() -> None:
    root = Path(__file__).parent.parent
    text = (root / "context/flows/deliver-ticket.md").read_text(encoding="utf-8")
    assert "commit_lint" in text
    # It must gate before the confirm step, not after.
    assert text.index("commit_lint") < text.index("## Step 3 — Confirm")
