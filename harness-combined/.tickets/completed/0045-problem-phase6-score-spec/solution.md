# Solution

**Ticket**: 0045
**Title**: Make /problem Phase 6 actually run the spec score check

## Approach

Fill in Phase 6's body: read score-spec.md, apply, display, fix-and-re-score up to two
passes with commits on the branch, then carry the final verdict into the Checkpoint 1
template. Strictly fewer human touches: BLOCKs get fixed while the design context is
hottest, before the lead ever sees the checkpoint.

## Components

| Component | Responsibility |
|-----------|----------------|
| commands/problem.md Phase 6 | Check + bounded fix loop + branch commits |
| commands/problem.md Checkpoint 1 template | Verdict line addition |
| tests/test_0045_phase6_docs.py | Grep guards for the new instructions |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Reuse score-spec.md verbatim | Single source of truth for checks; no duplication |
| Two-pass budget | Mirrors spec-remediation's bounded-budget principle |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Grep: Phase 6 reads and applies score-spec.md and shows the report |
| FR-2 | Unit | Grep: two-pass budget and residual-BLOCK reporting present |
| FR-3 | Unit | Grep: Checkpoint 1 template contains the verdict line |
| FR-4 | Unit | Grep: fix passes commit on the branch per Phase 5 convention |

## Tradeoffs

- **Chose in-session fixes over invoking spec-remediation machinery because**: Phase 6
  has the full design context and judgement; mechanical-only fixing is a build-time
  constraint that does not apply here.
- **Accepting risk of**: self-review blindness on fixes — the build-time score gate
  remains as the independent backstop.

## Risks

- Checkpoint 1 verbosity creep; the verdict is one line.

## Implementation Order

1. Write Phase 6 body and fix budget.
2. Extend Checkpoint 1 template.
3. Add docs tests; run suite.
