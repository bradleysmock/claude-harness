# Requirements

**Ticket**: 0050
**Title**: Testability rubric for score-spec (WARN tier)

## Functional Requirements

1. context/score-spec.md must add a seventh check, "FR testability", applied per FR:
   judge whether a failing test is derivable from the FR sentence alone (concrete
   actor, action, observable outcome); the report must list each flagged FR with a
   one-line reason.
2. The testability check must map only to WARN severity in the verdict rules; the
   existing six checks and their severities must be unchanged.
3. commands/refine.md interactive Step 2 must include testability-flagged FRs among
   the items it proactively surfaces for tightening.
4. The score-spec report format must include the per-FR testability line so the
   /problem Phase 6 display and Checkpoint 1 verdict (ticket 0045) carry it.

## Non-Functional Requirements

1. The rubric is executed by the model applying score-spec.md (no subagent, no new
   tooling).
2. Rubric wording must include two worked examples: one passing FR and one flagged FR
   with its reason, to anchor consistent judgement.

## Test Strategy

| Type | Rationale                                                    |
|------|----------------------------------------------------------------|
| Unit | Docs greps: check present, WARN-only mapping, report line, refine wiring, worked examples |

## Acceptance Criteria

- score-spec.md contains the testability check with WARN-only severity and two worked
  examples.
- Verdict rules text still grants BLOCK only to the original four BLOCK checks.
- refine.md names testability WARNs as a surfaced item class.

## Open Questions

- None.
