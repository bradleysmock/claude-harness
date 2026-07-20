# Problem Statement

**Ticket**: 0055
**Title**: Persist refine-touched flag to disk (Step S writes, Step B checks, deliver clears)
**Date**: 2026-07-12

## Problem

When autopilot's Step S clears a score-spec BLOCK via a semantic `/refine` pass
(`succeeded(autonomous=False)`), the flow says to "mark this run refine-touched" —
but the mark exists only in the running session's context. Step B's carve-out
(confirm the diff instead of auto-delivering) depends entirely on that in-memory
mark surviving until delivery.

## Impact

- Context compaction, `/clear`, a crash, or a fresh `/autopilot XXXX` resuming the
  ticket silently drops the mark — Step B then auto-delivers machine-adjusted,
  lead-unapproved scope unseen. This is fail-open on the exact condition the
  carve-out exists to prevent.
- Concurrent autopilots on the same ticket (observed repeatedly in this repo)
  never see a sibling session's mark.
- `autopilot-batch.md` declares refine-touched members out of scope but has no
  signal on disk to detect them.

## Success Criteria

- Step S persists a marker file in the ticket directory, committed on the branch,
  whenever the outcome is `succeeded(autonomous=False)`.
- Step B's carve-out decision reads the on-disk marker, not session memory.
- Delivery refuses to skip the confirmation prompt while the marker is present
  (fail-closed even if Step B is bypassed), and removes the marker as part of the
  delivery squash so a reopened ticket does not inherit a stale flag.
- Batch autopilot excludes members whose ticket directory carries the marker.
- Content-verification tests cover every touchpoint.

## Out of Scope

- Changing `/refine` semantics, the remediation budget, or score-spec checks.
- Retroactive markers for previously delivered tickets.
