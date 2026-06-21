# Problem Statement

**Ticket**: 0007
**Title**: Ticket List Command
**Date**: 2026-06-21

## Problem

Harness operators have no quick way to see a bird's-eye view of all tickets across both open and completed states. Currently, getting this overview requires navigating the filesystem and reading individual `status.md` files manually. There is no CLI command that aggregates and displays ticket metadata in a scannable format.

## Impact

- Harness operators waste time navigating `.tickets/` and `.tickets/completed/` directories to assess backlog state.
- Without a consolidated view, it is easy to miss stale tickets, duplicate work, or misjudge the effort remaining in a sprint.
- Onboarding new engineers to a project is harder when there is no quick backlog summary available.

## Success Criteria

- A `/ticket-list` command exists and prints a formatted table to stdout.
- Table columns include: ticket number, status, title, effort estimate, and last-updated date.
- Output covers both open tickets (`.tickets/`) and completed tickets (`.tickets/completed/`).
- `--open` flag filters to open tickets only.
- `--done` flag filters to completed tickets only.
- `--status <stage>` flag filters to tickets at a specific pipeline stage (e.g. `problem`, `solution`, `build`).
- Output resembles a Linear-style issue list (clean, aligned columns, no filesystem noise).
- Command handles missing fields in `status.md` gracefully (empty cell, no crash).

## Out of Scope

- Sorting or pagination beyond what fits in a terminal.
- Ticket editing or status mutation via this command.
- JSON or machine-readable output formats (future enhancement).
- Integration with any external issue tracker.
