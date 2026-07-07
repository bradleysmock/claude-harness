# Solution

**Ticket**: 0050
**Title**: Testability rubric for score-spec (WARN tier)

## Approach

Extend score-spec.md with a judged check kept deliberately out of the BLOCK path:
per-FR testability with anchored examples, reported in the existing structured format.
Wire the WARN output into refine's surfacing list. Ticket 0045's Phase 6 display then
carries it to Checkpoint 1 for free.

## Components

| Component | Responsibility |
|-----------|----------------|
| context/score-spec.md | Check 7 definition, worked examples, WARN-only severity, report line |
| commands/refine.md | Surface flagged FRs in interactive Step 2 |
| tests/test_0050_testability_docs.py | Grep guards for check, severity mapping, wiring |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| WARN-only judged check | Judged checks are non-deterministic; BLOCK authority stays deterministic so autopilot behavior is stable |
| Worked examples in the check text | Anchors model judgement across sessions; cheapest calibration tool |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Grep: check 7 present with per-FR reporting instruction |
| FR-2 | Unit | Grep: severity section maps testability to WARN; BLOCK set unchanged |
| FR-3 | Unit | Grep: refine Step 2 names testability WARNs |
| FR-4 | Unit | Grep: report template includes the testability line |

## Tradeoffs

- **Chose a judged WARN over an FR-template grammar because**: testability is
  semantic; a grammar would be gamed by phrasing while missing real vagueness.
- **Accepting risk of**: verdict variance between sessions — tolerable at WARN tier;
  the examples bound it.

## Risks

- Rubric inflation over time; the check text caps flags to genuinely untestable FRs
  and forbids style nits.

## Implementation Order

1. Write check 7 with examples and severity mapping in score-spec.md.
2. Update the report template.
3. Wire refine Step 2.
4. Docs tests.
