# Problem Statement

**Ticket**: 0018
**Title**: Milestone and Epic Grouping
**Date**: 2026-06-21

## Problem

The harness tracks individual tickets but has no concept of grouping related tickets into a named milestone or release.
Operators managing multi-ticket features cannot easily answer "how close is v2.0?" without manually scanning all tickets.
There is no single command to show completion percentage, remaining work, or per-milestone progress for stakeholders.

## Impact

- Harness operators cannot communicate release progress without exporting and aggregating data manually.
- Multi-ticket feature work (e.g., v2.0 launch) has no shared container — related tickets are invisible to each other.
- `/ticket-list` has no milestone filter, making it hard to isolate work belonging to a specific release.
- Without estimated-effort rollup, planning handoffs and communicating ETA to stakeholders is error-prone.

## Success Criteria

- `_milestones.md` file in `.tickets/` defines named milestones; the format is documented and enforced.
- Each ticket's `status.md` may include a `milestone:` field; a ticket belongs to at most one milestone.
- `/milestone` command prints: all milestones with completion percentage, done tickets, remaining tickets, and estimated remaining effort.
- `/ticket-list --milestone <name>` filters output to tickets tagged to that milestone.
- Milestones with no matching tickets produce an informative message rather than silent empty output.
- Effort rollup correctly handles missing effort fields (treats them as zero or unknown with a warning).

## Out of Scope

- Hierarchical milestone nesting (milestones-within-milestones).
- Automatic milestone creation from any source other than `_milestones.md`.
- GUI or web-based milestone visualization.
- Cross-repo or cross-project milestone aggregation.
- Milestone assignment to specs or build runs (only tickets are milestone-aware).
