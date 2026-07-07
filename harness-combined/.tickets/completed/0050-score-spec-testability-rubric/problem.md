# Problem Statement

**Ticket**: 0050
**Title**: Testability rubric for score-spec (WARN tier)
**Date**: 2026-07-05

## Problem

All six score-spec checks are structural — counts, imperative keywords, table
cross-references, placeholder markers. A vacuous functional requirement such as "The
system must work correctly" passes every check. Because the same artifacts drive spec
generation, weak FRs propagate into weak acceptance criteria, weak specs, and weak
tests, and the deficiency is discovered (if ever) only by the critic.

## Impact

- Structurally-valid but unimplementable requirements reach spec generation and
  produce vague constraints and untestable acceptance criteria.
- The gap between "score-spec PASS" and "actually buildable" is absorbed silently by
  the build phase, where fixing it is most expensive.

## Success Criteria

- score-spec judges each FR for testability and reports per-FR verdicts.
- The rubric can only WARN, never BLOCK — the deterministic checks keep sole BLOCK
  authority, so autopilot autonomy is unchanged.
- Refinement surfaces flagged FRs for tightening.

## Out of Scope

- Changing the BLOCK check set or verdict rules.
- Auto-rewriting flagged FRs (refine flows own revision).
