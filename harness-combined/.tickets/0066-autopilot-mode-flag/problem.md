# Problem Statement

**Ticket**: 0066
**Title**: Autopilot mode flag: build-ticket.md branches explicitly; shrink autopilot-ticket.md to mode plus steps S/A/B
**Date**: 2026-07-20

## Problem

`autopilot-ticket.md` reuses `build-ticket.md` by telling the model, in prose, to
watch for three in-flight conditions (score-spec BLOCK, repair exhaustion, clean
build) and redirect to its own Step S/A/B when one occurs. This is implicit
branching — correctness depends on the model noticing a narrative cue mid-read —
unlike the `DRY_RUN` pattern Step 7a already uses (`should_auto_repair(dry_run)`).

## Impact

- A missed interception point falls through to `build-ticket.md`'s fail-closed
  default (stop, ask the lead) even under autopilot, silently defeating it.
- Every future edit to a `build-ticket.md` stop point must be manually kept in
  sync with the matching interception prose in `autopilot-ticket.md`, or drift.
- `autopilot-ticket.md` restates `build-ticket.md`'s control flow narratively, so
  the two files can disagree about "normal" behavior.

## Success Criteria

- `build-ticket.md` reads an explicit mode signal (e.g. `MODE`) at all three
  lead-facing decision points — score-spec BLOCK, repair exhaustion, clean build
  — and branches on it directly, matching the `DRY_RUN` check's shape.
- Callers that never set the autopilot mode signal keep today's fail-closed
  behavior unchanged (regression guard).
- `autopilot-ticket.md` drops the "watch for" interception prose; it sets the
  mode signal, delegates, and defines Steps S/A/B only.
- Existing flow-doc tests still pass; a new test pins the explicit branches.

## Out of Scope

- `autopilot-batch.md`'s per-member override mechanics — untouched.
- `build-dry-run-ticket.md` / `DRY_RUN` itself — used only as precedent.
- Any change to repair-loop or critic logic beyond how the branch is detected.
