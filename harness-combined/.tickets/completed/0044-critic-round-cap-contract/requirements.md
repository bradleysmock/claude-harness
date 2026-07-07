# Requirements

**Ticket**: 0044
**Title**: Fix the critic agent's round-cap contract

## Functional Requirements

1. agents/critic.md must describe the Round parameter as caller-supplied, noting the
   design phase caps rounds at 2 (owned by /problem Phase 5) and the code phase sets
   round numbers per its repair loop with no cap enforced by the agent.
2. The critic agent definition must not instruct any behavior change based on round
   number beyond echoing it in the report header.
3. A docs-consistency test must assert agents/critic.md contains no unqualified
   "capped at 2" claim and that build-ticket.md Step 7a still documents rounds beyond 2.

## Non-Functional Requirements

1. Wording-only change; no flow logic or budgets change.

## Test Strategy

| Type | Rationale                                        |
|------|---------------------------------------------------|
| Unit | Grep assertions on agents/critic.md and build-ticket.md |

## Acceptance Criteria

- agents/critic.md states the per-phase round semantics.
- The docs test fails if an unqualified 2-round cap re-appears in the agent definition.

## Open Questions

- None.
