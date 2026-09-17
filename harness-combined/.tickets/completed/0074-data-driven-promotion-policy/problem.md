# Problem Statement

**Ticket**: 0074
**Title**: Data-driven promotion policy
**Date**: 2026-09-04

## Problem

"Which gates block delivery, and what happens when one fails" is expressed
procedurally, in more than one place: `commands/gate.md`'s fail-fast wiring,
the critic BLOCKER/MAJOR auto-repair branch, and an implicit assumption in
every suite runner that all configured gates are required and any failure
makes the run non-zero. Changing that policy — making a gate advisory, or
adding a "pause for human" disposition — means editing several call sites
instead of one.

## Impact

Anyone adjusting delivery policy (e.g. "lint should warn, not block" or
"security failures need a human, not auto-repair") must find and edit every
call site that encodes the current all-required/any-failure-blocks
assumption, risking drift between them. There is no single place to audit
"what blocks this project's delivery."

## Success Criteria

- A single declarative policy table (`gate name -> {required, on_block,
  depends_on}`) governs the pass/fail -> promote/block decision.
- One pure function, `evaluate_promotion`, takes gate results (and a policy)
  and returns a single `PromotionVerdict` — no I/O, no subprocess.
- Gate *execution* and scheduling are untouched; only the promotion decision
  is centralized.
- No `[policy]` block present reproduces today's exact behavior
  (all-required, any-failure-blocks) — the feature is additive.
- `commands/gate.md` and the build repair loop read the same verdict instead
  of each re-deriving pass/fail logic.
- A `pause_for_human` disposition routes through the existing
  exhausted-repair escalation halt, without inventing a new ticket status.

## Out of Scope

- Replacing the gate scheduler or its dependency-ordered execution.
- A general rules engine — the policy table is a flat, auditable list, not
  arbitrary logic.
- A new ticket status for "paused" — reuses the existing escalation halt.
