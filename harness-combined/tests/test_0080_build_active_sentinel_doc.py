"""Content-verification tests for build-ticket.md Step 2's `.active`
sentinel fix (ticket 0080).

The coverage gate's sidecar write depends on `.tickets/.active` (inside the
worktree — `server.py` derives `standards_path` as
`<directory>/.tickets/_standards.md`) naming the ticket. Step 2 previously
wrote it only in a rare fallback branch, with a bare relative path that's
ambiguous about cwd. These tests pin the fix's *position*, not just its
presence: a write grouped with the later `# cwd = .worktrees/XXXX-<slug>`
block would double the worktree path and silently reintroduce the bug on
every `/build`, unconditionally instead of only in the rare fallback.
"""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent.parent / "context" / "flows" / "build-ticket.md"

_CORRECT_ACTIVE_LINE = "echo 'XXXX-<slug>' > .worktrees/XXXX-<slug>/.tickets/.active"
_OLD_BARE_ACTIVE_LINE = "echo 'XXXX-<slug>' > .tickets/.active"
_CWD_ANNOTATION = "# cwd = .worktrees/XXXX-<slug>"
_CYCLE_CHECK_MARKER = "assert_acyclic(parse_deps(Path(\".tickets\")))"
_STEP2_HEADER = "## Step 2 — Resume the claim worktree (do not create one)"
_STEP3_HEADER = "## Step 3 — Load DAG and checkpoint"


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def _step2() -> str:
    content = _content()
    start = content.index(_STEP2_HEADER)
    end = content.index(_STEP3_HEADER, start)
    return content[start:end]


def test_step2_writes_the_correct_explicit_path() -> None:
    assert _CORRECT_ACTIVE_LINE in _step2()


def test_active_write_precedes_cycle_check() -> None:
    step2 = _step2()
    write_idx = step2.index(_CORRECT_ACTIVE_LINE)
    cycle_idx = step2.index(_CYCLE_CHECK_MARKER)
    assert write_idx < cycle_idx


def test_active_write_precedes_cwd_annotation() -> None:
    step2 = _step2()
    write_idx = step2.index(_CORRECT_ACTIVE_LINE)
    cwd_idx = step2.index(_CWD_ANNOTATION)
    assert write_idx < cwd_idx


def test_old_ambiguous_bare_path_line_is_gone() -> None:
    assert _OLD_BARE_ACTIVE_LINE not in _step2()


def test_active_write_appears_exactly_once() -> None:
    step2 = _step2()
    assert step2.count("echo 'XXXX-<slug>' >") == 1


def test_preserves_cycle_check_and_implementing_transition() -> None:
    step2 = _step2()
    assert _CYCLE_CHECK_MARKER in step2
    assert "TicketCyclicDependencyError" in step2
    assert 'Then transition `status: implementing`' in step2
    assert 'python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX implementing --push' in step2
    assert _CWD_ANNOTATION in step2


def test_preserves_fallback_worktree_add_line() -> None:
    step2 = _step2()
    assert "git worktree add .worktrees/XXXX-<slug> ticket/XXXX-<slug>" in step2
