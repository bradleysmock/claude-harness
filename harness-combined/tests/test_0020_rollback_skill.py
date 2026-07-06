"""Content-verification tests for skills/rollback/SKILL.md (ticket 0020).

/rollback is a model-interpreted Markdown skill: it reverts a delivered ticket's merge
commit via a standardized, fail-closed `git revert`. Its behavior is defined entirely in
the skill document, so these tests verify the doc documents every behavior required by
requirements.md FR-1..FR-14 and NFR-1..NFR-3, so the model executes the right steps.

Limitation: these tests verify the instructions exist, not that the model executes them
at runtime.
"""
from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent.parent / "skills" / "rollback" / "SKILL.md"


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def test_skill_file_exists() -> None:
    assert DOC.exists(), "skills/rollback/SKILL.md must exist"


def test_has_frontmatter_with_name_and_triggers() -> None:
    content = _content()
    assert content.startswith("---"), "SKILL.md must open with YAML frontmatter"
    head = content[: content.find("\n---", 3) + 4]
    assert "name: rollback" in head, "frontmatter must declare name: rollback"
    assert "TRIGGER" in head and "SKIP" in head, "description must carry TRIGGER and SKIP guidance"


# --- FR-1 / NFR-3: input validation is first, allow-list, prefix extraction ---

def test_fr1_validation_pattern_documented() -> None:
    content = _content()
    assert "^[0-9]{4}(-[a-z0-9-]+)?$" in content, "the allow-list validation regex must be documented"


def test_fr1_validation_is_first_and_fails_closed() -> None:
    content = _content()
    step0 = content.find("## Step 0")
    step1 = content.find("## Step 1")
    assert step0 >= 0 and step1 > step0, "Step 0 (validation) must exist and precede Step 1"
    lower = content.lower()
    # validation must be described as running before any git command
    assert "before any" in lower and "git command" in lower, \
        "validation must be documented as running before any git command"


def test_nfr1_mutating_steps_ordered_after_guards() -> None:
    """Fail-closed invariant (NFR-1/NFR-3): the two mutating steps must be positioned
    after the operator confirmation and the clean-tree pre-flight, not merely after Step 0."""
    content = _content()
    confirm = content.find("## Step 8")      # operator confirmation
    clean_tree = content.find("## Step 9")    # git status --porcelain pre-flight
    revert = content.find("## Step 10")       # git revert (first mutating command)
    commit = content.find("## Step 11")       # git commit (second mutating command)
    assert 0 <= confirm < clean_tree < revert < commit, \
        "confirmation (8) must precede clean-tree (9), which must precede revert (10) then commit (11)"


def test_nfr1_mutating_commands_come_after_preflight_text() -> None:
    """The literal mutating commands must appear later in the doc than the confirmation
    prompt and the clean-tree check — a reorder that moved them earlier would break fail-closed."""
    content = _content()
    confirm_prompt = content.find("(yes/no)")
    preflight = content.find("git status --porcelain")
    first_mutation = content.find("git revert --no-commit -m 1")
    assert 0 <= confirm_prompt < preflight < first_mutation, \
        "the revert command must be documented after both the yes/no prompt and the clean-tree check"


def test_fr1_prefix_extraction_documented() -> None:
    content = _content()
    lower = content.lower()
    assert "first four" in lower or "four-digit prefix" in lower, \
        "must document extracting the four-digit prefix"
    assert "discard" in lower and "slug" in lower, "must document discarding the slug suffix"


def test_nfr3_empty_argument_stops() -> None:
    content = _content()
    assert "empty" in content.lower(), "must document the empty-argument stop"


# --- FR-2: status resolution order and partial-archive guard ---

def test_fr2_completed_first_then_active() -> None:
    content = _content()
    assert ".tickets/completed/" in content, "must search the completed status file"
    assert ".tickets/XXXX-" in content, "must fall back to the active status file"
    completed_pos = content.find(".tickets/completed/")
    active_pos = content.find(".tickets/XXXX-*/status.md")
    assert completed_pos >= 0 and active_pos > completed_pos, \
        "completed status file must be searched before the active fallback"


def test_fr2_partial_archive_warns_and_stops() -> None:
    content = _content().lower()
    assert "partial-archive" in content, "must document the partial-archive state"
    assert "both" in content, "must document the both-exist condition"


def test_fr2_no_status_file_stops() -> None:
    content = _content().lower()
    assert "no ticket found" in content or "neither exists" in content, \
        "must document stopping when no status file is found"


# --- FR-3: done gate ---

def test_fr3_requires_done_status() -> None:
    content = _content()
    assert "status: done" in content or "status equals done" in content or "not `done`" in content, \
        "must require status: done"
    assert "Nothing to roll back" in content or "nothing to revert" in content.lower(), \
        "must warn and stop when the ticket is not delivered"


# --- FR-4: merge-commit search ---

def test_fr4_uses_merges_filter() -> None:
    content = _content()
    assert "--merges" in content, "must use the git log --merges filter"


def test_fr4_greps_ticket_branch_string() -> None:
    content = _content()
    assert '--grep "ticket/XXXX"' in content or "ticket/XXXX" in content, \
        "must grep for the ticket/XXXX branch string"


def test_fr4_one_hash_per_line_format() -> None:
    content = _content()
    assert '--pretty=format:"%H"' in content, "must request a one-full-hash-per-line format"
    assert "--oneline" in content, "must contrast against --oneline to explain the choice"


# --- FR-5 / FR-6: zero and multi match ---

def test_fr5_zero_match_stops() -> None:
    content = _content().lower()
    assert "zero matches" in content or "no merge commit found" in content, \
        "must warn and stop on zero matches"


def test_fr6_multi_match_lists_and_stops() -> None:
    content = _content()
    lower = content.lower()
    assert "more than one match" in lower or "multiple merge commits" in lower, \
        "must document the multi-match case"
    assert "refusing to guess" in lower or "ambiguous" in lower, "must refuse to guess on ambiguity"


# --- FR-7: subject verification ---

def test_fr7_subject_verification() -> None:
    content = _content()
    assert "git log -1 --pretty=format:'%s'" in content, "must fetch the subject line separately"
    assert "commit subject does not match expected pattern" in content, \
        "must report the exact subject-mismatch message"


# --- FR-8 / FR-9 / FR-10: display, dry-run, confirm ---

def test_fr8_displays_sha_and_subject() -> None:
    content = _content().lower()
    assert "subject" in content and "commit" in content, "must display the SHA and subject"


def test_fr9_dry_run_is_noop() -> None:
    content = _content()
    assert "--dry-run" in content, "must document the --dry-run flag"
    lower = content.lower()
    assert "no git-mutating command" in lower or "make no state change" in lower, \
        "dry-run must make no git change"


def test_fr10_confirmation_required() -> None:
    content = _content()
    assert "(yes/no)" in content, "must prompt yes/no"
    lower = content.lower()
    assert "affirmative" in lower, "only an affirmative answer proceeds"
    assert "without making any git change" in lower or "without any git change" in lower, \
        "a non-affirmative answer must make no git change"


# --- FR-11 / NFR-1: clean-tree pre-flight ---

def test_fr11_clean_tree_preflight() -> None:
    content = _content()
    assert "git status --porcelain" in content, "must run git status --porcelain before revert"
    assert "Working tree is not clean" in content, "must use the exact dirty-tree error message"


def test_nfr1_no_mutation_before_confirmation_or_dry_run() -> None:
    content = _content().lower()
    # the doc must repeatedly assert the fail-closed no-mutation property
    assert content.count("no git-mutating command") + content.count("no git command") >= 2, \
        "must assert the fail-closed no-mutation property on the guard paths"


# --- FR-12 / FR-13: revert + standardized message ---

def test_fr12_revert_no_commit_mainline() -> None:
    content = _content()
    assert "git revert --no-commit -m 1" in content, "must use git revert --no-commit -m 1"


def test_mainline_first_parent_assumption_documented() -> None:
    content = _content().lower()
    assert "first parent" in content, "must document the -m 1 first-parent selection"
    assert "mainline assumption" in content, "must surface the mainline first-parent coupling to /deliver"


def test_empty_revert_guard_documented() -> None:
    content = _content().lower()
    assert "already reverted" in content, "must guard the zero-exit empty-revert case before committing"
    assert "nothing to commit" in content, "must avoid creating an empty revert commit"


def test_fr12_exact_message_format_with_em_dash() -> None:
    content = _content()
    # Bind the U+2014 em-dash to the commit-message line itself, not to any of the ~30
    # prose em-dashes elsewhere in the doc. The exact message string must appear verbatim.
    message = 'revert(ticket): XXXX <title> — reverts merge commit <SHA>'
    assert message in content, "the exact commit-message format (with U+2014 em-dash) must appear verbatim"
    # And the message must not have regressed to a hyphen-minus or en-dash separator.
    assert 'revert(ticket): XXXX <title> - reverts' not in content, "separator must not be a hyphen-minus"
    assert 'revert(ticket): XXXX <title> – reverts' not in content, "separator must not be an en-dash"


def test_fr13_title_sourced_from_status() -> None:
    content = _content()
    assert "title:" in content, "must read the title: field from status.md"
    lower = content.lower()
    assert "missing or empty" in lower or "non-empty" in lower, \
        "must require the title to be present before committing the message"


# --- FR-14: conflict handling ---

def test_fr14_conflict_handling() -> None:
    content = _content()
    assert "git revert --continue" in content, "must instruct git revert --continue on conflict"
    assert "git revert --abort" in content, "must instruct git revert --abort on conflict"
    lower = content.lower()
    assert "do not auto-abort" in lower or "does not auto-abort" in lower or "not auto-abort" in lower, \
        "must state that it does not auto-abort"


# --- NFR-2 + schema citation + worktree scope ---

def test_nfr2_argument_lists_only() -> None:
    content = _content().lower()
    assert "argument list" in content, "must state git commands use argument lists"


def test_cites_schema_source_and_repo_root() -> None:
    content = _content()
    assert "harness-reference.md" in content, "must cite harness-reference.md as the status.md schema source"
    assert "main repo root" in content, "must note running from the main repo root"
