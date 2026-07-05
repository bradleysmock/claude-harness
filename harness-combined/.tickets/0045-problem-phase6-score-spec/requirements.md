# Requirements

**Ticket**: 0045
**Title**: Make /problem Phase 6 actually run the spec score check

## Functional Requirements

1. commands/problem.md Phase 6 must instruct reading context/score-spec.md in full and
   applying its checks to the worktree's requirements.md and solution.md, displaying
   the structured per-check report.
2. On a BLOCK verdict, Phase 6 must revise the artifacts and re-score before
   presenting Checkpoint 1, bounded to at most two fix passes; a residual BLOCK after
   the budget must be reported inside the Checkpoint 1 summary rather than hidden.
3. The Checkpoint 1 template must include a score-spec verdict line (PASS, WARN with
   named checks, or residual BLOCK with named checks).
4. Artifact revisions made by Phase 6 must be committed on the branch with the design
   commit convention from Phase 5.

## Non-Functional Requirements

1. No change to score-spec.md itself or to the build-time gate.
2. Phase 6 fixes reuse full design-session context; no subagent is spawned.

## Test Strategy

| Type | Rationale                                                  |
|------|--------------------------------------------------------------|
| Unit | Docs greps: Phase 6 check instruction, fix budget, checkpoint verdict line, branch commit |

## Acceptance Criteria

- commands/problem.md Phase 6 names score-spec.md and the two-pass fix budget.
- The Checkpoint 1 block in problem.md contains the verdict line.
- Existing docs tests pass.

## Open Questions

- None.
