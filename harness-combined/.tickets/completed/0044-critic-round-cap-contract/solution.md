# Solution

**Ticket**: 0044
**Title**: Fix the critic agent's round-cap contract

## Approach

Replace the round line in agents/critic.md with per-phase semantics and add a small
grep-based docs test. Round budgets remain where they already live: /problem Phase 5
(design, max 2) and build-ticket.md Step 7a plus repair-escalation.md (code, caller-
numbered).

## Components

| Component | Responsibility |
|-----------|----------------|
| agents/critic.md | Corrected Round parameter description |
| tests/test_0044_critic_round_docs.py | Guards agent/caller agreement |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Caller-owned budgets | Matches every other loop bound in the harness (MAX_REPAIR_ATTEMPTS) |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Grep: per-phase wording present in agents/critic.md |
| FR-2 | Unit | Grep: no round-conditional behavior instruction in the agent definition |
| FR-3 | Unit | Grep: no unqualified cap text; Step 7a round wording intact |

## Tradeoffs

- **Chose wording fix over adding an agent-side cap parameter because**: the agent has
  no legitimate use for a cap; budgets belong to the loops that spawn it.

## Risks

- None material; smallest ticket in the batch.

## Implementation Order

1. Edit agents/critic.md.
2. Add the docs test; run suite.
