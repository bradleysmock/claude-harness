# Problem Statement

**Ticket**: 0001
**Title**: Archive Completed and Cancelled Tickets
**Date**: 2026-06-11

## Problem

As the number of tickets grows, the `.tickets/` directory becomes cluttered with completed and cancelled work alongside active tickets. This makes it harder for engineers to quickly identify which tickets are open and in-progress at a glance, reducing operational clarity in the pipeline.

## Impact

- Engineers scanning `.tickets/` must visually filter completed work from active tickets.
- No tooling distinction between live work and historical artifacts.
- Status commands (`/status`, `harness_status`) must sift through all tickets, increasing noise.

## Success Criteria

- Delivered tickets are moved to `.tickets/completed/` after delivery.
- Cancelled tickets are moved to `.tickets/completed/` (or a separate `.tickets/cancelled/`) after cancellation.
- No ticket in an incomplete status (problem, requirements, solution, spec, building, escalated) is ever moved.
- Reopened tickets move back to `.tickets/` root.
- All harness commands that enumerate tickets continue to work correctly after archiving.
- The archive operation is idempotent — archiving an already-archived ticket is a no-op or safe error.

## Out of Scope

- UI or dashboard changes beyond CLI/pipeline commands.
- Retroactive bulk-archiving of existing tickets (manual or optional).
- Separate subdirectory distinction between delivered vs. cancelled (both go to `completed/`).
