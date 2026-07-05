# Problem Statement

**Ticket**: 0045
**Title**: Make /problem Phase 6 actually run the spec score check
**Date**: 2026-07-05

## Problem

commands/problem.md Phase 6 is titled "Spec Score Check" but its body only says to
present Checkpoint 1. The score-spec gate first runs at /write-spec or /build time —
so a structurally deficient spec sails through Checkpoint 1, gets lead approval, and
then BLOCKs at build time. In autopilot this triggers the Step S remediation machinery
for artifacts that were fully reviewable one phase earlier.

## Impact

- The lead approves designs at Checkpoint 1 that the harness itself will reject
  minutes later, wasting an approval cycle.
- Autopilot's spec-remediation budget is consumed on defects /problem could have fixed
  in-session with full design context.
- The phase name promises a check that does not happen — a doc-reader trap.

## Success Criteria

- Phase 6 applies the score-spec checks and fixes BLOCKs before Checkpoint 1.
- The Checkpoint 1 summary displays the score-spec verdict.
- Build-time BLOCKs become rare (only from post-approval artifact edits).

## Out of Scope

- Changing score-spec's checks or verdict rules (ticket 0050 extends them).
- Removing the build-time score gate — it stays as the fail-closed backstop.
