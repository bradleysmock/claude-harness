# Problem Statement

**Ticket**: 0044
**Title**: Fix the critic agent's round-cap contract
**Date**: 2026-07-05

## Problem

agents/critic.md tells the critic "Round: 1 or 2 (rounds are capped at 2)", but its
callers legitimately exceed that: build-ticket.md Step 7a re-spawns the critic up to
MAX_REPAIR_ATTEMPTS additional rounds, and repair-escalation.md Phases 1 and 2 add up
to two further batches. The 2-round cap is a design-phase rule owned by /problem
Phase 5, wrongly stated as a property of the agent itself.

## Impact

- A literal critic could refuse Round 3 or treat the cap as license to stop reviewing
  mid-repair-loop, silently weakening the post-build verification chain.
- The contradiction is a drift trap: future edits to either side deepen the mismatch.

## Success Criteria

- The agent definition states round semantics per phase: design rounds capped at 2 by
  the caller; code rounds supplied by the caller with no agent-side cap.
- Caller flows and the agent definition agree, guarded by a docs test.

## Out of Scope

- Changing actual round budgets in any flow.
- Critic report content or severity vocabulary.
