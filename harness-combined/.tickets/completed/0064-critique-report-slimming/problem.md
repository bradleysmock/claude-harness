# Problem Statement

**Ticket**: 0064
**Title**: Critique report slimming
**Date**: 2026-07-20

## Problem

Ticket 0049 taught `/critique` to write its full report to
`.harness/critiques/` and print only a compact terminal summary. Three
other call sites never adopted that: `build-ticket.md` Step 7 (post-build),
`build-dry-run-ticket.md` Steps 4-5 (design), `autopilot-batch.md` Step 3
(batch) — each dumps the full report into the session, burning context and
burying the verdict.

## Impact

Leads running `/build`, `/build --dry-run`, or `autopilot` pay for the
full report every turn and scroll past per-finding detail to find the
verdict. Repair loops and multi-ticket batches compound this per call.

## Success Criteria

- `build-ticket.md`'s post-build critic keeps its full append to committed
  `critic-findings.md`, but prints only header+verdict+table.
- `build-dry-run-ticket.md` (persists no critic detail today) writes its
  full report to `.harness/critiques/`; the dry-run report shows only
  header+verdict+table plus a pointer.
- `autopilot-batch.md` (also persists nothing today) writes its full
  combined report to `.harness/critiques/` with a resolved batch slug and
  pointers on every member's `critic-findings.md`; prints only
  header+verdict+table.
- `/status`'s recent-critiques listing picks up the new writes unchanged.

## Out of Scope

- `/review`'s interactive critic stream — conversational, not a report.
- `commands/problem.md` Checkpoint 1 — already a narrative summary.
- Finding schema, severity tiers, `.harness/critiques/` naming (owned by
  0049/0058/0062).
