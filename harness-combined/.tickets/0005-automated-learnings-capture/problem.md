# Problem Statement

**Ticket**: 0005
**Title**: Automated Learnings Capture
**Date**: 2026-06-21

## Problem

After `/deliver` completes, recurring gate-failure patterns and critic findings are discarded — the lead must manually inspect past runs and hand-author `_learnings.md` entries. This friction means the must-fix pattern library grows only when the lead proactively invests time, which in practice means it rarely grows at all.

## Impact

- Harness operators miss repeated failure patterns that `_learnings.md` would have caught upfront.
- The lead bears all authoring burden; the machine's failure trail in `memory.db` is never surfaced as actionable learning.
- Quality gains from past mistakes are not systematically fed back into the pipeline.

## Success Criteria

- After `/deliver` completes, candidate `_learnings.md` lines are proposed automatically, derived from the ticket's `gate-findings.md` and any critic findings.
- A standalone `/harvest-learnings` command surfaces recurring gate-failure patterns from `memory.db` as additional candidates.
- The lead reviews each candidate and accepts or rejects it; accepted entries are appended to `.tickets/_learnings.md`.
- No entries are written to `_learnings.md` without explicit lead approval.
- Proposed entries are formatted as valid `_learnings.md` lines ready to paste.

## Out of Scope

- Automatic editing of `_learnings.md` without lead review.
- Analysis of critic findings from tickets other than the one being delivered.
- Retroactive batch-processing of historical tickets.
