---
name: status
description: Show the combined state of harness work — open tickets with their statuses plus recent standalone spec/build runs and failure-memory summary. TRIGGER when the user asks "what's open", "what's in flight", "what's the status", "show me tickets", "where are we?", or any general progress check across the harness pipeline. SKIP when the user wants a single ticket's detailed state (read its `status.md` directly), when they want implementation-order ranking only (use /ticket-status), and when they want a debug postmortem on a failed run (use the debug skill).
---

# Status skill — combined pipeline view

Show the current state of all work in the project: SDLC tickets + standalone spec/build runs + failure memory.

Read `.harness/config.py` if it exists to get `PROJECT_ROOT` (default `.`).

## Step 1 — Ticket status (SDLC workflow)

Scan `.tickets/*/status.md` for active tickets (those not in `completed/`). Exclude any with status `done` or `cancelled` — they belong in the Completed section below. For each active ticket, report: ticket number, title, status.

### Active Tickets

| Ticket | Title | Status |
|--------|-------|--------|
| XXXX   | ...   | implementing / review-ready / ... |

If there are `review-ready` tickets, remind the user: invoke `/gate XXXX` for fresh gate findings, then `/deliver XXXX` once approved.

If there are `changes-requested` tickets, remind the user: invoke `/build XXXX` to resume work in the existing worktree.

### Completed Tickets

Scan `.tickets/completed/*/status.md`. For each, report: ticket number, title, terminal status.

| Ticket | Title | Status |
|--------|-------|--------|
| XXXX   | ...   | done / cancelled |

If there are no completed tickets, omit this section. Use `/reopen XXXX` to resume work on a completed ticket.

## Step 2 — Spec/build status (standalone workflow)

Call `harness_status(project_root)` (MCP tool).

Format:
- ✓ passed runs — spec-id, timestamp
- ⚠ escalated runs — spec-id, failing gate name, timestamp

If there are passed runs awaiting write-out, remind the user: run `/deliver <run-id>`.
If there are escalated runs, remind the user: invoke the **debug** skill to investigate.

## Step 3 — Failure memory summary

If `.harness/memory.db` exists, note: "Failure memory: present" (do a quick file existence check; do not query the DB).

## Output shape

Keep the report compact. Active tickets table + optional completed tickets table + spec/build status + one-line memory note. Do not narrate; the user will pull on whichever thread matters next.
