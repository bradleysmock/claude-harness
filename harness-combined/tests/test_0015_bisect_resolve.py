"""Unit + integration tests for bin/bisect-resolve.sh (ticket 0015).

bisect-resolve.sh is the private, executable implementation detail behind the
/bisect command. These tests exercise its subcommands directly (requirements.md
FR-1..FR-12, NFR-1..NFR-3): boundary classification/resolution, ticket->merge-commit
resolution with the subject-anchored false-positive guard, test-command precedence,
multi-word --run wrapping, culprit->ticket attribution via merge ancestry, and a
full bisect run against a fixture repo whose regression commit is known.

Each git fixture is built in an isolated tmp_path so the tests never depend on the
harness repo's own history.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "bin" / "bisect-resolve.sh"

# UTF-8 locale so the em-dash (U+2014) in the culprit output has a stable encoding.
_ENV = {**os.environ, "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}

# Culprit-line prefix, kept as a constant so expected strings are built by
# concatenation rather than interpolation.
_PREFIX = "Regression introduced in commit "


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=cwd,
        env=_ENV,
        capture_output=True,
        text=True,
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=_ENV, capture_output=True, text=True, check=True
    ).stdout.strip()


def _init(cwd: Path) -> None:
    _git(cwd, "init", "-q", "-b", "main")
    _git(cwd, "config", "user.email", "dev@example.com")
    _git(cwd, "config", "user.name", "Dev")


def _commit(cwd: Path, path: str, content: str, message: str) -> str:
    (cwd / path).write_text(content, encoding="utf-8")
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-qm", message)
    return _git(cwd, "rev-parse", "HEAD")


def _ticket_repo(cwd: Path, *, deleted_branch: bool = True, title: bool = True) -> dict[str, str]:
    """A repo with a ticket/0010 branch merged into main via a --no-ff merge
    commit, an interior regression commit, and (optionally) the branch pruned to
    mimic /deliver. Returns key SHAs."""
    _init(cwd)
    base = _commit(cwd, "f.txt", "0\n", "c0 base")
    _git(cwd, "checkout", "-q", "-b", "ticket/0010-widget")
    _commit(cwd, "f.txt", "1\n", "c1 good")
    culprit = _commit(cwd, "f.txt", "BROKEN\n", "c2 regression")
    _commit(cwd, "g.txt", "x\n", "c3 more")
    _git(cwd, "checkout", "-q", "main")
    _git(cwd, "merge", "-q", "--no-ff", "-m", "Merge ticket/0010-widget: add widget", "ticket/0010-widget")
    merge = _git(cwd, "rev-parse", "HEAD")
    if deleted_branch:
        _git(cwd, "branch", "-q", "-D", "ticket/0010-widget")
    tdir = cwd / ".tickets" / "0010-widget"
    tdir.mkdir(parents=True)
    body = "status: done\nticket: 0010\n"
    if title:
        body += "title: Widget Feature\n"
    (tdir / "status.md").write_text(body, encoding="utf-8")
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-qm", "archive 0010 metadata")
    return {"base": base, "culprit": culprit, "merge": merge}


# ── FR-1/FR-2: classification ─────────────────────────────────────────────────

def test_classify_four_digit_is_ticket(tmp_path: Path) -> None:
    assert _run("classify-boundary", "0010", cwd=tmp_path).stdout.strip() == "ticket"


def test_classify_ref_is_ref(tmp_path: Path) -> None:
    assert _run("classify-boundary", "HEAD~3", cwd=tmp_path).stdout.strip() == "ref"


# ── FR-3/NFR-2: validation before any git use ─────────────────────────────────

def test_resolve_ticket_rejects_non_four_digit(tmp_path: Path) -> None:
    r = _run("resolve-ticket", "0010abc", cwd=tmp_path)
    assert r.returncode != 0
    assert "invalid ticket number" in r.stderr


def test_resolve_ticket_rejects_injection_without_executing(tmp_path: Path) -> None:
    # A shell-injection payload must be rejected at validation and never run.
    marker = tmp_path / "pwned"
    payload = "0010; touch " + str(marker)
    r = _run("resolve-ticket", payload, cwd=tmp_path)
    assert r.returncode != 0
    assert "invalid ticket number" in r.stderr
    assert not marker.exists(), "injection payload must never execute (NFR-2)"


# ── FR-4: subject-anchored merge-commit resolution ────────────────────────────

def test_resolve_ticket_returns_merge_sha(tmp_path: Path) -> None:
    shas = _ticket_repo(tmp_path)
    assert _run("resolve-ticket", "0010", cwd=tmp_path).stdout.strip() == shas["merge"]


def test_resolve_ticket_ignores_body_only_mention(tmp_path: Path) -> None:
    shas = _ticket_repo(tmp_path)
    # A later commit that mentions the ticket only in its body must not match.
    (tmp_path / "note.txt").write_text("n\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "unrelated", "-m", "see ticket/0010-widget for context")
    assert _run("resolve-ticket", "0010", cwd=tmp_path).stdout.strip() == shas["merge"]


def test_resolve_ticket_no_merge_commit_errors(tmp_path: Path) -> None:
    _ticket_repo(tmp_path)
    r = _run("resolve-ticket", "0011", cwd=tmp_path)
    assert r.returncode != 0
    assert "no merge commit found for ticket 0011" in r.stderr


# ── FR-1/FR-2/FR-3: boundary resolution ───────────────────────────────────────

def test_resolve_boundary_valid_ref(tmp_path: Path) -> None:
    _ticket_repo(tmp_path)
    head = _git(tmp_path, "rev-parse", "HEAD")
    assert _run("resolve-boundary", "HEAD", cwd=tmp_path).stdout.strip() == head


def test_resolve_boundary_bogus_ref_errors(tmp_path: Path) -> None:
    _ticket_repo(tmp_path)
    r = _run("resolve-boundary", "no-such-ref", cwd=tmp_path)
    assert r.returncode != 0
    assert "not a valid" in r.stderr


# ── FR-6: test-command precedence ─────────────────────────────────────────────

def test_testcmd_run_flag_wins(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    assert _run("resolve-testcmd", "--run", "ctest", cwd=tmp_path).stdout.strip() == "ctest"


def test_testcmd_settings_json(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        '{"test_command": "make check"}\n', encoding="utf-8"
    )
    assert _run("resolve-testcmd", cwd=tmp_path).stdout.strip() == "make check"


def test_testcmd_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    assert _run("resolve-testcmd", cwd=tmp_path).stdout.strip() == "npm test"


def test_testcmd_pyproject_with_pytest_section(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    assert _run("resolve-testcmd", cwd=tmp_path).stdout.strip() == "pytest"


def test_testcmd_pyproject_without_pytest_section_falls_through(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.black]\nline-length = 100\n", encoding="utf-8")
    r = _run("resolve-testcmd", cwd=tmp_path)
    assert r.returncode != 0, "pyproject without a pytest section must NOT yield pytest"
    assert "no test command" in r.stderr


def test_testcmd_none_errors_with_guidance(tmp_path: Path) -> None:
    r = _run("resolve-testcmd", cwd=tmp_path)
    assert r.returncode != 0
    assert "--run" in r.stderr and "settings.json" in r.stderr


# ── FR-7: multi-word wrapping ─────────────────────────────────────────────────

def test_wrap_multiword_creates_script(tmp_path: Path) -> None:
    r = _run("wrap-testcmd", "pytest -x tests/", cwd=tmp_path)
    path = Path(r.stdout.strip())
    assert path.exists() and path != Path("pytest -x tests/")
    body = path.read_text(encoding="utf-8")
    assert body.startswith("#!/usr/bin/env bash")
    assert "pytest -x tests/" in body
    assert os.access(path, os.X_OK), "wrapper must be executable"
    path.unlink()


def test_wrap_single_word_passed_directly(tmp_path: Path) -> None:
    assert _run("wrap-testcmd", "pytest", cwd=tmp_path).stdout.strip() == "pytest"


# ── FR-10/FR-11: culprit attribution ──────────────────────────────────────────

def test_map_culprit_interior_commit_walks_to_merge(tmp_path: Path) -> None:
    shas = _ticket_repo(tmp_path)  # branch deleted post-merge
    out = _run("map-culprit", shas["culprit"], cwd=tmp_path).stdout.strip()
    assert out == _PREFIX + shas["culprit"] + " — part of ticket 0010 (Widget Feature)"


def test_map_culprit_merge_commit_attributed_directly(tmp_path: Path) -> None:
    shas = _ticket_repo(tmp_path)
    out = _run("map-culprit", shas["merge"], cwd=tmp_path).stdout.strip()
    assert out == _PREFIX + shas["merge"] + " — part of ticket 0010 (Widget Feature)"


def test_map_culprit_no_title_uses_bare_number(tmp_path: Path) -> None:
    shas = _ticket_repo(tmp_path, title=False)
    out = _run("map-culprit", shas["culprit"], cwd=tmp_path).stdout.strip()
    assert out == _PREFIX + shas["culprit"] + " — part of ticket 0010"
    assert "(" not in out


def test_map_culprit_attributed_ticket_without_status_md(tmp_path: Path) -> None:
    # A ticket is attributed via the merge subject, but no .tickets/XXXX-*/status.md
    # exists at the tip. FR-11 requires the bare-number fallback, NOT an error.
    _init(tmp_path)
    _commit(tmp_path, "f.txt", "0\n", "c0 base")
    _git(tmp_path, "checkout", "-q", "-b", "ticket/0033-orphan")
    culprit = _commit(tmp_path, "f.txt", "BROKEN\n", "c1 regression")
    _git(tmp_path, "checkout", "-q", "main")
    _git(tmp_path, "merge", "-q", "--no-ff", "-m", "Merge ticket/0033-orphan: no metadata", "ticket/0033-orphan")
    _git(tmp_path, "branch", "-q", "-D", "ticket/0033-orphan")
    r = _run("map-culprit", culprit, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == _PREFIX + culprit + " — part of ticket 0033"


def test_map_culprit_pre_ticket_commit_not_linked(tmp_path: Path) -> None:
    shas = _ticket_repo(tmp_path)
    out = _run("map-culprit", shas["base"], cwd=tmp_path).stdout.strip()
    assert out == _PREFIX + shas["base"] + " — not linked to a ticket"


def test_map_culprit_uses_em_dash(tmp_path: Path) -> None:
    shas = _ticket_repo(tmp_path)
    out = _run("map-culprit", shas["culprit"], cwd=tmp_path).stdout
    assert "—" in out and " - " not in out


# ── FR-5/FR-8/FR-9/FR-12/NFR-1: full bisect run ───────────────────────────────

def _bisect_repo(cwd: Path) -> dict[str, str]:
    """10-commit ticket branch merged to main; commit 7 introduces the regression.
    Returns base SHA (good boundary) and the known regression SHA."""
    _init(cwd)
    base = _commit(cwd, "code.txt", "line0\n", "c0 base")
    _git(cwd, "checkout", "-q", "-b", "ticket/0007-feature")
    regression = ""
    for i in range(1, 11):
        # Distinct content per commit (so each commit is non-empty); the marker
        # "BROKEN" first appears at commit 7 and persists thereafter.
        marker = "BROKEN " if i >= 7 else "line "
        content = marker + str(i) + "\n"
        sha = _commit(cwd, "code.txt", content, "c" + str(i) + " work")
        if i == 7:
            regression = sha
    _git(cwd, "checkout", "-q", "main")
    _git(cwd, "merge", "-q", "--no-ff", "-m", "Merge ticket/0007-feature: the feature", "ticket/0007-feature")
    _git(cwd, "branch", "-q", "-D", "ticket/0007-feature")
    tdir = cwd / ".tickets" / "0007-feature"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text("status: done\nticket: 0007\ntitle: The Feature\n", encoding="utf-8")
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-qm", "archive 0007")
    return {"base": base, "regression": regression}


def test_run_finds_regression_and_attributes(tmp_path: Path) -> None:
    shas = _bisect_repo(tmp_path)
    test = tmp_path / "istest.sh"
    # exit non-zero (bad) when the regression marker is present.
    test.write_text("#!/usr/bin/env bash\n! grep -q BROKEN code.txt\n", encoding="utf-8")
    test.chmod(0o755)
    head_before = _git(tmp_path, "rev-parse", "HEAD")

    r = _run("run", "--good", shas["base"], "--run", str(test), cwd=tmp_path)

    assert r.returncode == 0, r.stderr
    assert shas["regression"] in r.stdout
    assert "part of ticket 0007 (The Feature)" in r.stdout
    # NFR-1: repo restored, no lingering bisect state, no double-fire stderr.
    assert _git(tmp_path, "rev-parse", "HEAD") == head_before
    assert not (tmp_path / ".git" / "BISECT_LOG").exists()
    assert "We are not bisecting" not in r.stderr


def test_run_multiword_command_end_to_end(tmp_path: Path) -> None:
    # FR-7 acceptance: a multi-word --run is wrapped in a temp script and executes
    # correctly through git bisect run. `grep -q -v BROKEN code.txt` exits 0 (good)
    # while the single line lacks the marker and 1 (bad) once it appears.
    shas = _bisect_repo(tmp_path)
    head_before = _git(tmp_path, "rev-parse", "HEAD")
    r = _run("run", "--good", shas["base"], "--run", "grep -q -v BROKEN code.txt", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert shas["regression"] in r.stdout
    assert "part of ticket 0007 (The Feature)" in r.stdout
    assert _git(tmp_path, "rev-parse", "HEAD") == head_before
    assert not (tmp_path / ".git" / "BISECT_LOG").exists()


def test_run_cleanup_fires_on_mid_bisect_error(tmp_path: Path) -> None:
    # FR-12/NFR-1: the trap must restore the repo even when the bisect aborts
    # mid-run. A test command exiting 128 makes git bisect run abort; the command
    # then finds no culprit and errors, but the EXIT trap must still reset.
    shas = _bisect_repo(tmp_path)
    abort = tmp_path / "abort.sh"
    abort.write_text("#!/usr/bin/env bash\nexit 128\n", encoding="utf-8")
    abort.chmod(0o755)
    head_before = _git(tmp_path, "rev-parse", "HEAD")
    r = _run("run", "--good", shas["base"], "--run", str(abort), cwd=tmp_path)
    assert r.returncode != 0
    assert _git(tmp_path, "rev-parse", "HEAD") == head_before, "trap must restore HEAD on mid-bisect error"
    assert not (tmp_path / ".git" / "BISECT_LOG").exists(), "trap must clear bisect state on error"
    assert "We are not bisecting" not in r.stderr


def test_run_missing_flag_value_errors_cleanly(tmp_path: Path) -> None:
    # A flag with no value must produce the clean 'requires a value' error, not a
    # silent set -e abort.
    r = _run("run", "--good", cwd=tmp_path)
    assert r.returncode != 0
    assert "requires a value" in r.stderr


def test_run_requires_good(tmp_path: Path) -> None:
    _bisect_repo(tmp_path)
    r = _run("run", "--run", "true", cwd=tmp_path)
    assert r.returncode != 0
    assert "--good" in r.stderr


def test_run_errors_before_bisect_on_bad_boundary(tmp_path: Path) -> None:
    _bisect_repo(tmp_path)
    r = _run("run", "--good", "no-such-ref", "--run", "true", cwd=tmp_path)
    assert r.returncode != 0
    assert not (tmp_path / ".git" / "BISECT_LOG").exists(), "must error before starting bisect"
