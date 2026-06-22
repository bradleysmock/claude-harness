# Problem Statement

**Ticket**: 0035
**Title**: Sprint Planning Command
**Date**: 2026-06-21

## Problem

The harness tracks a backlog of open tickets but provides no way to group them
into time-boxed batches. Leads must mentally sequence work across effort
estimates and dependency ordering, a tedious error-prone task as backlog depth
grows. Without a sprint planning tool, the harness lacks the sequencing
ceremony that turns a flat backlog into an actionable delivery schedule.

## Impact

- Harness operators spending time manually grouping tickets when a backlog
  reaches double digits, reducing planning efficiency.
- Dependency ordering violations (starting a ticket whose dependency is
  not yet done) remain undetected until `/build` blocks mid-sprint.
- No shared artifact captures the agreed sprint sequence, making mid-sprint
  reprioritization opaque.

## Success Criteria

- `/sprint` reads `effort` and `depends-on` fields from each open ticket's
  `status.md` and produces a sprint plan assigning tickets to ordered sprint
  slots.
- Sprint duration is configurable (default: 1 week). Capacity assumptions
  are transparent in the output.
- Tickets blocked by unfinished dependencies are placed no earlier than the
  sprint after the latest dependency resolves.
- Output is a formatted Markdown sprint plan: sprint number, ticket list,
  total estimated effort per sprint.
- The command works read-only — it never modifies any ticket artifact.

## Out of Scope

- Persisting the sprint plan as a file or modifying `status.md`.
- Automated ticket assignment or resource scheduling (people/teams).
- Partial-done effort carryover within a sprint.
- Integration with external project management tools (Linear, Jira, etc.).
