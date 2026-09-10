"""Content-verification for ticket 0081's Phase 5 panel fan-out in problem.md.

Asserts Phase 5 resolves panels in-session, hands every spawned agent a
`Panels:` field, branches single-agent vs one-agent-per-panel on the non-Core
panel count, verifies each report before merging, concatenates without dedup,
re-detects fresh in round 2, and keeps the 2-pass Checkpoint-1 budget — while
Phase 5's pre-existing preconditions, evaluations, and commit sub-section stay
intact.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PROBLEM = (_ROOT / "commands" / "problem.md").read_text(encoding="utf-8")

ANNOUNCEMENT_FORMAT = "Panels active:"


def _phase_5() -> str:
    start = _PROBLEM.index("## Phase 5 — Critic Loop")
    end = _PROBLEM.index("## Phase 6 — Spec Score Check", start)
    return _PROBLEM[start:end]


def _subsection(heading: str) -> str:
    """One `###` sub-section of Phase 5, so an assertion can be branch-scoped."""
    phase_5 = _phase_5()
    start = phase_5.index(heading)
    tail = phase_5.index("\n### ", start + len(heading))
    return phase_5[start:tail]


# --- FR-1: in-session detection and candidate disposition --------------------


def test_phase_5_runs_panel_detect_itself_in_session() -> None:
    phase_5 = _phase_5()
    assert "panel_detect.py" in phase_5
    assert "--root" in phase_5
    assert "--design" in phase_5
    assert "in-session" in phase_5.lower()


def test_phase_5_infers_the_file_scope_from_solution_md() -> None:
    lowered = _phase_5().lower()
    assert "solution.md" in lowered
    assert "infer" in lowered


def test_phase_5_dispositions_every_candidate_with_a_one_line_reason() -> None:
    lowered = _phase_5().lower()
    assert "candidates" in lowered
    assert "one-line reason" in lowered
    assert "skipped" in lowered


# --- FR-2 / FR-3: every agent receives the resolved list ---------------------


def test_every_spawned_agent_receives_a_panels_field() -> None:
    phase_5 = _phase_5()
    assert "every agent Phase 5 spawns, in either branch, receives the fully resolved list" in phase_5
    assert "not optional here" in phase_5
    assert "re-derive" in phase_5.lower()


def test_the_shared_brief_carries_the_panels_field() -> None:
    brief = _subsection("### The shared brief")
    assert "Panels: **<this agent's assigned panels, comma-separated>**" in brief
    assert "subagent_type: critic" in brief


def test_single_agent_branch_is_documented_as_equivalent_to_today() -> None:
    branch_a = _subsection("### Branch A")
    assert "fewer than 2" in branch_a
    assert "Spawn exactly one critic agent" in branch_a
    assert "comma-joined" in branch_a
    assert "same total review depth" in branch_a
    assert "pre-resolved list instead of re-deriving it" in branch_a


# --- FR-4 / NFR-2: the fan-out branch ----------------------------------------


def test_fanout_threshold_is_two_or_more_non_core_panels() -> None:
    lowered = _phase_5().lower()
    assert "non-core" in lowered
    assert "2 or more" in lowered
    assert "one agent per" in lowered


def test_fanout_spawns_are_parallel_calls_in_a_single_message() -> None:
    lowered = _phase_5().lower()
    assert "single message" in lowered
    assert "parallel" in lowered
    assert "sequential" in lowered


def test_only_the_core_agent_carries_the_design_specific_evaluations() -> None:
    phase_5 = _phase_5()
    assert "Panels: Core" in phase_5
    lowered = phase_5.lower()
    assert "design-specific evaluations" in lowered
    assert "no added evaluations" in lowered or "not appended" in lowered


# --- FR-7: per-agent verification before merging -----------------------------


def test_phase_5_verifies_report_presence_per_agent() -> None:
    verify = _subsection("### Verify every report before merging")
    assert "A missing, errored, or timed-out agent fails this check" in verify
    assert "an empty response is a missing report, not a clean review" in verify


def test_verification_applies_to_both_branches_not_only_the_fanout() -> None:
    verify = _subsection("### Verify every report before merging")
    assert "**every** agent Phase 5 spawns, in **both** branches" in verify
    branch_a = _subsection("### Branch A")
    assert "Verification still applies" in branch_a
    assert "which is unconditional" in branch_a


def test_panel_scope_is_verified_against_the_findings_not_only_the_announcement() -> None:
    verify = _subsection("### Verify every report before merging")
    assert "self-declared" in verify
    assert "subset" in verify
    assert "critic_finding_parser.py" in verify


def test_the_halt_retry_is_bounded_to_one_respawn_per_agent() -> None:
    verify = _subsection("### Verify every report before merging")
    assert "one re-spawn per failing agent" in verify
    assert "do not re-spawn a third time" in verify
    assert "the second failure is the lead's call" in verify.lower()


def test_phase_5_verifies_an_exact_panels_active_match() -> None:
    phase_5 = _phase_5()
    assert ANNOUNCEMENT_FORMAT in phase_5
    lowered = phase_5.lower()
    assert "exactly" in lowered
    assert "no more and no fewer" in lowered


def test_verification_failure_halts_the_round_rather_than_merging() -> None:
    lowered = _phase_5().lower()
    assert "halt" in lowered
    assert "never" in lowered and "silently" in lowered


def test_a_halted_round_does_not_consume_a_revision_pass() -> None:
    lowered = _phase_5().lower()
    assert "retry" in lowered
    assert "does not consume" in lowered or "spends no" in lowered


# --- FR-8: concatenation-only merge ------------------------------------------


def test_merge_is_concatenation_with_no_fuzzy_dedup() -> None:
    lowered = _phase_5().lower()
    assert "concatenat" in lowered
    assert "no fuzzy dedup" in lowered


def test_merged_header_names_every_contributing_panel_once() -> None:
    merge = _subsection("### Merge the verified reports")
    assert "naming every contributing panel **once**" in merge
    assert "in the order the panels were resolved" in merge


def test_cross_panel_content_overlap_is_an_accepted_tradeoff() -> None:
    lowered = _phase_5().lower()
    assert "overlap" in lowered
    assert "accepted" in lowered


# --- FR-9 / FR-10: round 2 and the budget ------------------------------------


def test_round_2_re_runs_detection_fresh_against_the_revised_solution() -> None:
    lowered = _phase_5().lower()
    assert "round 2" in lowered
    assert "fresh" in lowered
    assert "revised" in lowered


def test_a_changed_fanout_between_rounds_is_surfaced_in_one_line() -> None:
    lowered = _phase_5().lower()
    assert "differs from round 1" in lowered or "differs from round 1's" in lowered
    assert "one line" in lowered


def test_budget_stays_two_total_revision_passes_regardless_of_fanout() -> None:
    phase_5 = _phase_5()
    assert "**Maximum 2 rounds.**" in phase_5
    lowered = phase_5.lower()
    assert "never counts as more than one round" in lowered


# --- FR-11: Secondary escalation stays manual --------------------------------


def test_secondary_escalation_is_manual_and_orchestrator_optional() -> None:
    lowered = _phase_5().lower()
    assert "secondary" in lowered
    assert "manual" in lowered
    assert "merged reports" in lowered


# --- no regression: pre-existing Phase 5 content -----------------------------


def test_artifact_existence_precondition_survives() -> None:
    phase_5 = _phase_5()
    assert "verify that all three artifact files exist and are non-empty" in phase_5
    assert "If any file is missing or empty, fix the write before proceeding." in phase_5


def test_the_five_design_specific_evaluations_survive_verbatim() -> None:
    phase_5 = _phase_5()
    for evaluation in (
        "1. **Requirements coverage** — does the solution address every FR and success criterion? Are acceptance criteria testable as designed?",
        "2. **Test plan gaps** — what scenarios would the loaded panels' experts flag as missing?",
        "3. **Tech choices** — are there better-fit alternatives given the constraints?",
        "4. **Security design** — apply McGraw: are trust boundaries correct? Does the design fail closed?",
        "5. **Implementation order risks** — dependencies or sequencing that could cause rework.",
    ):
        assert evaluation in phase_5, f"design-specific evaluation must survive verbatim: {evaluation[:40]!r}"


def test_critic_brief_reference_and_subagent_type_survive() -> None:
    phase_5 = _phase_5()
    assert "subagent_type: critic" in phase_5
    assert "context/critic-brief.md" in phase_5
    assert "Phase: **design**" in phase_5


def test_design_artifact_commit_subsection_survives() -> None:
    phase_5 = _phase_5()
    assert "### Commit the design artifacts (on the branch)" in phase_5
    assert 'git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX design (status: solution)"' in phase_5
    assert "git -C .worktrees/XXXX-<slug> push" in phase_5
