# Requirements

**Ticket**: 0001
**Title**: Archive Completed and Cancelled Tickets

## Functional Requirements

1. The system must move a ticket directory from `.tickets/<XXXX-slug>/` to `.tickets/completed/<XXXX-slug>/` when its status transitions to `done`.
2. The system must move a ticket directory from `.tickets/<XXXX-slug>/` to `.tickets/completed/<XXXX-slug>/` when its status transitions to `cancelled`.
3. The system must never move a ticket whose status is any value other than `done` or `cancelled`.
4. The system must move a ticket directory from `.tickets/completed/<XXXX-slug>/` back to `.tickets/<XXXX-slug>/` when `/reopen XXXX` is run; the restored ticket's status must be set to `solution`.
5. All harness commands that enumerate, locate, or read tickets by ID or slug must search both `.tickets/` and `.tickets/completed/` transparently.
6. The archive operation must be idempotent — if a ticket is already in the target location, the operation succeeds without error. If both root and completed copies exist simultaneously (partial-move state), the root copy is authoritative and a warning is emitted.
7. The `/deliver` command must trigger archiving as part of its completion flow.
8. The `/status` and `/ticket-status` commands must include archived tickets in a distinct "Completed" section, visually separated from active tickets.

## Non-Functional Requirements

1. Archive moves must be atomic (OS-level rename/move), not copy-then-delete, to prevent partial state on failure.
2. Ticket lookup by ID or slug must not silently fail when the ticket is in the completed subfolder.

## Test Strategy

| Type        | Rationale                                                                 |
|-------------|---------------------------------------------------------------------------|
| Unit        | Archive/unarchive path computation; status eligibility guard              |
| Integration | `/deliver` triggers move; reopened ticket moves back; `harness_status` finds tickets in both locations |

## Acceptance Criteria

- After `/deliver XXXX` completes, `.tickets/XXXX-slug/` does not exist and `.tickets/completed/XXXX-slug/` does, with `status: done`.
- After `/cancel XXXX` completes, `.tickets/XXXX-slug/` does not exist and `.tickets/completed/XXXX-slug/` does, with `status: cancelled`.
- After `/reopen XXXX` on an archived ticket, `.tickets/completed/XXXX-slug/` does not exist, `.tickets/XXXX-slug/` does, and `status.md` contains `status: solution`.
- `/status` output contains an "Active Tickets" section and a "Completed Tickets" section; no `done` or `cancelled` ticket appears under "Active Tickets"; no `implementing` or `review-ready` ticket appears under "Completed Tickets".
- The following commands accept a ticket ID and resolve it correctly when the ticket is in `.tickets/completed/`: `/deliver`, `/build`, `/write-spec`, `/gate`, `/cancel`, `/requirements`, `/solution`, `/refine`. The flow files `build-ticket.md` and `write-spec-ticket.md` also resolve from both locations.
- Attempting to archive an already-archived ticket (root absent, completed present) produces no error and no data change.
- If both `.tickets/XXXX-slug/` and `.tickets/completed/XXXX-slug/` exist, the root copy is treated as authoritative and a warning is shown.
- No ticket with status other than `done` or `cancelled` is present in `.tickets/completed/`.

## Open Questions

None.
