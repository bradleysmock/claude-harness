"""Integration tests for the /changelog command (commands/changelog.md).

The command's logic lives entirely in a single fenced ```bash block. These tests
extract that block and run it against throwaway git-repo fixtures, asserting on the
generated CHANGELOG.md, stdout, stderr, and exit code. Commit dates and the output
date are pinned so every scenario is deterministic.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

COMMAND_FILE = Path(__file__).parent.parent / "commands" / "changelog.md"
_DEVNULL = subprocess.DEVNULL


def _extract_script() -> str:
    text = COMMAND_FILE.read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)\n```", text, re.DOTALL)
    assert len(blocks) == 1, "commands/changelog.md must contain exactly one ```bash block"
    return blocks[0]


SCRIPT = _extract_script()


def _git(repo: Path, *args: str, date: str | None = None) -> None:
    env = dict(os.environ)
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=repo, check=True, env=env,
                   stdout=_DEVNULL, stderr=_DEVNULL)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    return repo


def _commit(repo: Path, subject: str, date: str = "2026-06-01T12:00:00") -> None:
    _git(repo, "commit", "-q", "--allow-empty", "-m", subject, date=date)


def _tag(repo: Path, name: str) -> None:
    _git(repo, "tag", name)


def _completed_ticket(repo: Path, dirname: str, title: str, updated: str | None = None) -> Path:
    d = repo / ".tickets" / "completed" / dirname
    d.mkdir(parents=True, exist_ok=True)
    lines = ["status: done", f"ticket: {dirname[:4]}", f"title: {title}"]
    if updated is not None:
        lines.append(f"updated: {updated}")
    (d / "status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


def _run(repo: Path, tmp_path: Path, date: str = "2026-07-05") -> subprocess.CompletedProcess:
    script = tmp_path / "_changelog.sh"
    script.write_text(SCRIPT, encoding="utf-8")
    env = dict(os.environ)
    env["CHANGELOG_DATE"] = date
    return subprocess.run(["bash", str(script)], cwd=repo,
                          capture_output=True, text=True, env=env)


def _changelog(repo: Path) -> str:
    return (repo / "CHANGELOG.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #

def test_command_file_has_single_bash_block():
    assert "set -euo pipefail" in SCRIPT
    # every user-controlled expansion the script uses must be double-quoted
    assert 'git log "$range"' in SCRIPT
    # the tag ref file is stamped with POSIX `touch -t`, never invoked with `-d`
    assert 'touch -t "$stamp"' in SCRIPT
    assert not re.search(r"touch\s+-d\b", SCRIPT)


# --------------------------------------------------------------------------- #
# FR-2 boundary
# --------------------------------------------------------------------------- #

def test_tag_boundary_groups_entries_since_tag(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "chore: seed", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")  # tag date 2026-06-01
    _commit(repo, "feat: add login page", date="2026-06-10T12:00:00")
    _commit(repo, "fix(scope): correct math", date="2026-06-11T12:00:00")
    _completed_ticket(repo, "0002-feat-inventory", "Inventory module", updated="2026-06-15")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "## [Unreleased] - 2026-07-05" in cl
    assert "### feat" in cl and "- feat: add login page" in cl
    assert "- Inventory module" in cl
    assert "### fix" in cl and "- fix\\(scope\\): correct math" in cl
    # the pre-tag seed commit must not appear
    assert "chore: seed" not in cl


def test_no_tag_covers_all_history(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat: first", date="2026-05-01T12:00:00")
    _commit(repo, "fix: second", date="2026-05-02T12:00:00")
    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "- feat: first" in cl
    assert "- fix: second" in cl


def test_no_boundary_fails_closed(tmp_path):
    repo = _init_repo(tmp_path)  # no commits at all
    r = _run(repo, tmp_path)
    assert r.returncode != 0
    assert "boundary" in r.stderr.lower()
    assert not (repo / "CHANGELOG.md").exists()


# --------------------------------------------------------------------------- #
# FR-3 ticket collection + date filter + find fallback
# --------------------------------------------------------------------------- #

def test_ticket_date_filtering(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "chore: seed", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")  # 2026-06-01
    _completed_ticket(repo, "0001-feat-before", "Before tag", updated="2026-05-01")
    _completed_ticket(repo, "0002-feat-after-a", "After tag A", updated="2026-06-15")
    _completed_ticket(repo, "0003-feat-after-b", "After tag B", updated="2026-06-20")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "- After tag A" in cl
    assert "- After tag B" in cl
    assert "Before tag" not in cl


def test_ticket_find_newer_fallback_when_updated_absent(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "chore: seed", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")  # tag ref mtime ~ 2026-06-01, ticket dir created "now" => newer
    _completed_ticket(repo, "0004-feat-nodate", "No date ticket", updated=None)

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "- No date ticket" in _changelog(repo)


def test_status_with_duplicate_title_lines_does_not_abort(tmp_path):
    # Regression: a status.md with two `title:` lines must not SIGPIPE-abort the
    # command under `set -e -o pipefail`; the first title is used.
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    d = repo / ".tickets" / "completed" / "0010-feat-dup"
    d.mkdir(parents=True)
    (d / "status.md").write_text(
        "status: done\ntitle: First title\ntitle: Second title\nupdated: 2026-06-10\n",
        encoding="utf-8")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "- First title" in cl
    assert "Second title" not in cl


# --------------------------------------------------------------------------- #
# FR-4 / FR-5 categorization
# --------------------------------------------------------------------------- #

def test_commit_categorization(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _commit(repo, "feat: a feature", date="2026-06-02T12:00:00")
    _commit(repo, "fix(api): a bugfix", date="2026-06-03T12:00:00")
    _commit(repo, "just a bare message", date="2026-06-04T12:00:00")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    feat_idx = cl.index("### feat")
    fix_idx = cl.index("### fix")
    other_idx = cl.index("### other")
    assert cl.index("- feat: a feature") > feat_idx
    assert cl.index("- fix\\(api\\): a bugfix") > fix_idx
    assert cl.index("- just a bare message") > other_idx


def test_ticket_slug_type_inference(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _completed_ticket(repo, "0005-feat-add-login", "Add login", updated="2026-06-10")
    _completed_ticket(repo, "0006-my-feature", "My feature", updated="2026-06-10")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert cl.index("- Add login") > cl.index("### feat")
    assert cl.index("- My feature") > cl.index("### other")


# --------------------------------------------------------------------------- #
# FR-6 dedup
# --------------------------------------------------------------------------- #

def test_dedup_ticket_wins_over_matching_commit(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _commit(repo, "feat: add login page", date="2026-06-05T12:00:00")
    _completed_ticket(repo, "0007-feat-login", "Add login page", updated="2026-06-06")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert cl.lower().count("add login page") == 1  # commit dropped, ticket kept
    assert "- Add login page" in cl
    assert "- feat: add login page" not in cl


def test_dedup_key_with_leading_dash(tmp_path):
    # Regression: the dedup grep must treat a normalized key beginning with '-'
    # as data, not an option flag, or the commit is silently never deduplicated.
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _commit(repo, "feat: -n flag support", date="2026-06-05T12:00:00")
    _completed_ticket(repo, "0011-feat-nflag", "-n flag support", updated="2026-06-06")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert cl.lower().count("-n flag support") == 1  # deduped: ticket kept
    assert "- feat: -n flag support" not in cl


def test_no_dedup_when_normalized_differs(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _commit(repo, "fix: offbyone", date="2026-06-05T12:00:00")
    _completed_ticket(repo, "0008-fix-obo", "Fix: off-by-one", updated="2026-06-06")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "- fix: offbyone" in cl
    assert "- Fix: off-by-one" in cl


# --------------------------------------------------------------------------- #
# Sanitizer
# --------------------------------------------------------------------------- #

def test_sanitizer_escapes_and_does_not_trigger_idempotency(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _commit(repo, "[Unreleased] - 2026-06-21", date="2026-06-05T12:00:00")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "- \\[Unreleased\\] - 2026-06-21" in cl
    # exactly one real heading, the crafted subject did not create a second block
    assert cl.count("## [Unreleased]") == 1


def test_sanitizer_escapes_all_structural_chars(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _completed_ticket(repo, "0009-feat-x", "Title with (parens) and <tags> and [brackets]",
                      updated="2026-06-10")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "\\(parens\\)" in cl
    assert "\\<tags\\>" in cl
    assert "\\[brackets\\]" in cl


# --------------------------------------------------------------------------- #
# FR-7 formatting
# --------------------------------------------------------------------------- #

def test_empty_subsections_omitted(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _commit(repo, "feat: only a feature", date="2026-06-05T12:00:00")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "### feat" in cl
    assert "### fix" not in cl
    assert "### chore" not in cl
    assert "### other" not in cl


# --------------------------------------------------------------------------- #
# FR-8 writer boundary cases
# --------------------------------------------------------------------------- #

def test_changelog_created_when_absent(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat: x", date="2026-06-01T12:00:00")
    assert not (repo / "CHANGELOG.md").exists()
    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    assert (repo / "CHANGELOG.md").exists()


def test_prepended_above_existing_versioned_release(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat: new thing", date="2026-06-01T12:00:00")
    (repo / "CHANGELOG.md").write_text(
        "## [1.0.0] - 2026-01-01\n\n### feat\n- old thing\n", encoding="utf-8")
    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert cl.index("## [Unreleased]") < cl.index("## [1.0.0]")
    assert "- old thing" in cl  # existing content preserved


def test_replace_unreleased_through_eof(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat: new thing", date="2026-06-01T12:00:00")
    (repo / "CHANGELOG.md").write_text(
        "## [1.0.0] - 2026-01-01\n\n### feat\n- shipped\n\n"
        "## [Unreleased] - 2026-05-05\n\n### fix\n- stale entry\n",
        encoding="utf-8")
    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert cl.count("## [Unreleased]") == 1
    assert "- stale entry" not in cl        # old unreleased body replaced
    assert "- feat: new thing" in cl
    assert "- shipped" in cl                 # versioned release preserved above
    assert cl.index("## [1.0.0]") < cl.index("## [Unreleased]")


# --------------------------------------------------------------------------- #
# FR-9 idempotency
# --------------------------------------------------------------------------- #

def test_idempotent_single_block_with_warning(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat: x", date="2026-06-01T12:00:00")
    r1 = _run(repo, tmp_path)
    assert r1.returncode == 0, r1.stderr
    r2 = _run(repo, tmp_path)
    assert r2.returncode == 0, r2.stderr
    cl = _changelog(repo)
    assert cl.count("## [Unreleased]") == 1
    assert "replac" in r2.stderr.lower()


def test_head_equals_tag_no_crash(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")  # HEAD == tag, no new commits, no tickets
    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    cl = _changelog(repo)
    assert "## [Unreleased] - 2026-07-05" in cl
    assert "### feat" not in cl  # nothing to report


# --------------------------------------------------------------------------- #
# FR-10 stdout mirrors the written block
# --------------------------------------------------------------------------- #

def test_stdout_matches_written_block(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat: x", date="2026-06-01T12:00:00")
    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    block = r.stdout
    cl = _changelog(repo)
    assert cl.startswith(block.rstrip("\n"))


# --------------------------------------------------------------------------- #
# Shell safety
# --------------------------------------------------------------------------- #

def test_injection_in_commit_subject_is_not_executed(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    _tag(repo, "v0.1")
    _commit(repo, "feat: pwn $(touch INJECTED) ; touch ALSO", date="2026-06-05T12:00:00")

    r = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    assert not (repo / "INJECTED").exists()
    assert not (repo / "ALSO").exists()


def test_tag_name_with_metacharacter_is_quoted(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "root", date="2026-06-01T12:00:00")
    # git permits ';' and '$' '(' ')' in tag names; ensure no word-splitting/injection
    try:
        _tag(repo, "v0.1;$(touch TAGPWNED)")
    except subprocess.CalledProcessError:
        pytest.skip("git rejected the metacharacter tag name on this platform")
    _commit(repo, "feat: later", date="2026-06-05T12:00:00")

    r = _run(repo, tmp_path)
    # the command must not crash-execute the injected token
    assert not (repo / "TAGPWNED").exists()
    assert r.returncode in (0, 1)  # tolerate a clean fail-closed, but never injection
