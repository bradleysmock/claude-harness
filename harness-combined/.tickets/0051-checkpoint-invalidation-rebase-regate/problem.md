# Problem Statement

**Ticket**: 0051
**Title**: Checkpoint invalidation on spec edits and post-rebase re-gating
**Date**: 2026-07-05

## Problem

Two staleness gaps let previously-green state stand in for current verification.
First, checkpoints store only completed spec IDs with no content fingerprint — the
debug skill's Class A/B remedies explicitly propose editing a spec and re-running
/build, but the resumed build skips the edited spec as already passed. Second,
deliver-ticket Step 7 rebases other in-flight worktrees after a delivery and
unconditionally downgrades review-ready tickets to implementing with a note that
"gates are invalidated" — nothing re-runs them, and a clean rebase forces rework
ceremony while a semantically-conflicting one relies on someone noticing.

## Impact

- Spec fixes recommended by /debug are silently ignored on the next build.
- Post-delivery rebases either demote clean tickets needlessly or let semantic
  conflicts ride to delivery unverified.

## Success Criteria

- Editing a spec file invalidates its checkpoint entry automatically.
- Rebased worktrees are re-gated automatically; status downgrades happen only on
  actual gate failure.

## Out of Scope

- The delivering ticket's own pre-merge freshness (ticket 0008 owns that).
- DAG-level invalidation of downstream specs (follow-up candidate).
