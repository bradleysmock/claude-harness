"""Content-verification for ticket 0067's build-ticket.md Step 7a wiring.

Asserts the prep sub-step (harvest prior findings, capture diff, call
gates.incremental_scope) is documented before item 5's re-spawn, the
fail-closed fallback is documented, and Step 7's round-1 spawn text is
unaffected (no `Mode: incremental` marker there).
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BUILD = (_ROOT / "context" / "flows" / "build-ticket.md").read_text(encoding="utf-8")


def _section(doc: str, start_marker: str, end_marker: str) -> str:
    start = doc.index(start_marker)
    end = doc.index(end_marker, start + len(start_marker))
    return doc[start:end]


def test_step_7a_prep_substep_precedes_item_5_respawn() -> None:
    step_7a = _section(_BUILD, "### Step 7a", "### Step 7b")
    prep_idx = step_7a.index("Prep the incremental brief")
    respawn_idx = step_7a.index("Re-spawn the critic subagent")
    assert prep_idx < respawn_idx


def test_step_7a_prep_substep_reuses_0062_parser() -> None:
    step_7a = _section(_BUILD, "### Step 7a", "### Step 7b")
    assert "gates.critic_reconciler.latest_section" in step_7a
    assert "gates.critic_finding_parser.parse_critic_findings" in step_7a


def test_step_7a_prep_substep_captures_diff_against_head_not_main() -> None:
    step_7a = _section(_BUILD, "### Step 7a", "### Step 7b")
    prep_block = step_7a[step_7a.index("Prep the incremental brief") :]
    assert "git -C .worktrees/XXXX-<slug> diff HEAD~1 HEAD" in prep_block
    assert "never a diff against `main`" in prep_block


def test_step_7a_prep_substep_calls_incremental_scope_module() -> None:
    step_7a = _section(_BUILD, "### Step 7a", "### Step 7b")
    assert "gates.incremental_scope.touched_files_from_diff" in step_7a
    assert "gates.incremental_scope.format_incremental_brief" in step_7a


def test_step_7a_documents_fail_closed_fallback() -> None:
    step_7a = _section(_BUILD, "### Step 7a", "### Step 7b")
    lower = step_7a.lower()
    assert "fail-closed check" in lower
    assert "no `mode: incremental` marker" in lower


def test_step_7_round_1_spawn_has_no_incremental_marker() -> None:
    step_7 = _section(_BUILD, "## Step 7 —", "### Step 7a")
    assert "Mode: incremental" not in step_7
