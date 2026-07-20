# Problem Statement

**Ticket**: 0067
**Title**: Incremental critic rounds: rounds 2+ review repair diff, not the full worktree
**Date**: 2026-07-20

## Problem

- `/build`'s post-build critic loop (`build-ticket.md` Step 7/7a) re-spawns the critic subagent on every repair round with an instruction to read the entire worktree implementation and tests again — even when the round only touched the files needed to fix the prior round's findings.
- Ticket 0062 (stable critic finding IDs) lets the repair loop classify a round's findings as fixed/persisted/new against the prior round, but it only changes what happens *after* the critic runs — the critic is still asked to re-read the full worktree every round.
- Every repair round therefore pays full-worktree read + panel-reload cost to re-verify a handful of `file:line` fixes.

## Impact

- Token/cost and latency scale with `MAX_REPAIR_ATTEMPTS` × worktree size instead of with the size of what actually changed — expensive on large worktrees or long repair loops.
- The lead sees no difference in review depth for a 2-line fix vs. a fresh implementation, making round-over-round critic cost hard to reason about or budget for.

## Success Criteria

- Round 1 of every build's critic loop is unchanged: full-worktree scope, all panels, full Step 2.5 baseline checks.
- Repair-loop rounds 2+ (`Step 7a` re-spawns) give the critic only the round's own diff and the prior round's persisted BLOCKER/MAJOR findings (via 0062's existing parser) — not a full-worktree read instruction.
- Round 2+ still correctly reports which prior findings are fixed and flags new must-fix issues introduced by the round's own diff.
- Panel selection for round 2+ is scoped to the diff's touched files, not the full worktree's file set.

## Out of Scope

- Changing round 1's scope or the design-review (`/problem` Phase 5) critic loop — both stay full-scope.
- Changing 0062's reconciliation/marker format — 0067 consumes it, does not modify it.
- Changing the automated gate's full-worktree re-run (`gate_run_on_dir`) each round — only the critic's read scope changes.
