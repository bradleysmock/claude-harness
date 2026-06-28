"""Integration-style tests for the spec-remediation decision pipeline.

These exercise the *code* surface that `autopilot-ticket.md` Step S and
`context/spec-remediation.md` drive — classify → remediate_mechanical → finders —
against realistic requirements/solution fixtures, asserting the documented
autonomous / refine / bail routing at the code boundary. The flow's git commits
and score-spec re-runs are agent-executed markdown and are out of scope here.
"""

from __future__ import annotations

from gates.spec_remediate import (
    classify,
    nonimperative_fr_numbers,
    phantom_fr_numbers,
    remediate_mechanical,
    uncovered_fr_numbers,
)

# A ticket whose only BLOCKs are mechanical: FR-2 is non-imperative, FR-3 has no
# Test Plan row, and the table carries a phantom FR-9 row.
MECHANICAL_REQ = """\
# Requirements

## Functional Requirements

1. The system must intercept the BLOCK verdict.
2. The classifier may bucket each failing check by recipe.
3. The mechanical fixers must run in a single pass.

## Acceptance Criteria

- Builds with no lead intervention.
- Interactive build still hard-stops.
"""

MECHANICAL_SOL = """\
# Solution

## Test Plan

| Requirement | Test Type   | Scenario(s)                     |
|-------------|-------------|---------------------------------|
| FR-1        | Integration | Interception fires.             |
| FR-2        | Unit        | Classifier labels checks.       |
| FR-9        | Unit        | Phantom — FR-9 does not exist.  |

## Implementation Order

1. Build it.
"""


def _report(**checks: str) -> str:
    return "\n".join(f"[{v}] {k}" for k, v in checks.items())


def test_mechanical_only_block_clears_autonomously() -> None:
    # FR-1 / FR-3 / FR-4 / FR-7 / FR-9 autonomous path: the mechanical pass clears
    # every structural defect, leaving nothing for /refine.
    report = _report(
        **{"Imperative language": "BLOCK", "Test-plan coverage": "BLOCK"}
    )
    plan = classify(report)
    assert plan.semantic == [] and not plan.must_bail  # autonomous, no refine

    new_req, new_sol, announcements = remediate_mechanical(MECHANICAL_REQ, MECHANICAL_SOL)
    assert nonimperative_fr_numbers(new_req) == []
    assert uncovered_fr_numbers(new_req, new_sol) == []
    assert phantom_fr_numbers(new_req, new_sol) == []
    # One audit line per edit: FR-2 substitute + FR-3 append + FR-9 remove.
    assert len(announcements) == 3


def test_semantic_block_is_left_for_refine() -> None:
    # FR-5 / FR-9 refine path: a placeholder / FR-count BLOCK is semantic — the
    # mechanical pass must not touch it, so the flow routes to /refine
    # (autonomous=False).
    report = _report(**{"No placeholders": "BLOCK", "FR count": "BLOCK"})
    plan = classify(report)
    assert set(plan.semantic) == {"No placeholders", "FR count"}
    assert plan.mechanical == []
    # On structurally-clean artifacts the mechanical pass is a pure no-op: it
    # cannot resolve a semantic check, so the refine hand-off is required.
    clean_req, clean_sol, _ = remediate_mechanical(MECHANICAL_REQ, MECHANICAL_SOL)
    again_req, again_sol, announcements = remediate_mechanical(clean_req, clean_sol)
    assert announcements == []
    assert again_req == clean_req and again_sol == clean_sol


def test_unrecognised_block_bails_without_fixing() -> None:
    # FR-6 / FR-8 fail-closed: an unknown BLOCK check short-circuits to bail; the
    # presence of a fixable mechanical check alongside it does not rescue the run.
    report = _report(
        **{"Test-plan coverage": "BLOCK", "Architecture smell": "BLOCK"}
    )
    plan = classify(report)
    assert plan.must_bail is True
    assert plan.hard_stop == ["Architecture smell"]
