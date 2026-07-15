---
description: Run $ARGUMENTS through the full autonomous pipeline: spec generation (if needed), build-wi
---
Run `$ARGUMENTS` through the full autonomous pipeline: spec generation (if needed), build-with-extended-repair, and auto-deliver on success.

Requires the ticket to be at `status: solution`. If not, stop and tell the lead to run `/problem XXXX` first.

## Mode selection — single vs. batch

Count the 4-digit ticket IDs in `$ARGUMENTS`:

- **One ID (or none)** → single-ticket mode. Resolve as in "Ticket Resolution" below, then follow `autopilot-ticket.md`.
- **Two or more IDs** → **batch mode**: build all of them into one integration worktree, test them together, and deliver in a single atomic push (one squashed commit per member). Confirm **every** named ticket is at `status: solution` (resolve each under `.tickets/<id>*/` only — not `completed/`). If any is not at `solution`, stop and list the offenders. Then announce "Autopilot batch mode for XXXX + YYYY + … (lead: XXXX-slug)", read `/Users/bradley/workspaces/claude-harness/harness-combined/context/flows/autopilot-batch.md` in full, and follow it. Do **not** read `autopilot-ticket.md` in this case.

## Ticket Resolution

If `$ARGUMENTS` begins with four digits, scan `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/` if not found (diagnostic fallback only — any ticket found there will fail the `status: solution` check, giving a clear error rather than "not found"). Confirm the matched ticket is at `status: solution`. If the status is not `solution`, stop and tell the lead to run `/problem XXXX` first.

Read status via the **Ticket resolution** rule in `/Users/bradley/workspaces/claude-harness/harness-combined/context/harness-reference.md`: when a worktree `.worktrees/XXXX-<slug>` exists, its `.tickets/` copy of `status.md` is authoritative; the root copy shows only claim/terminal states, so a claimed-and-designed ticket reads `solution` only in the worktree.

If `$ARGUMENTS` is empty, scan `.tickets/` (not `.tickets/completed/`) for tickets with `status: solution`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before proceeding.

If no ticket is found, stop and report.

State the resolved ticket in one sentence — "Autopilot mode for XXXX-slug" — then read `/Users/bradley/workspaces/claude-harness/harness-combined/context/flows/autopilot-ticket.md` in full and follow it. (This single-ticket path is unchanged; batch mode is handled above via `autopilot-batch.md`.)
