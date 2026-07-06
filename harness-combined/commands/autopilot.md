Run `$ARGUMENTS` through the full autonomous pipeline: spec generation (if needed), build-with-extended-repair, and auto-deliver on success.

Requires the ticket to be at `status: solution`. If not, stop and tell the lead to run `/problem XXXX` first.

## Ticket Resolution

If `$ARGUMENTS` begins with four digits, scan `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/` if not found (diagnostic fallback only — any ticket found there will fail the `status: solution` check, giving a clear error rather than "not found"). Confirm the matched ticket is at `status: solution`. If the status is not `solution`, stop and tell the lead to run `/problem XXXX` first.

Read status via the **Ticket resolution** rule in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`: when a worktree `.worktrees/XXXX-<slug>` exists, its `.tickets/` copy of `status.md` is authoritative; the root copy shows only claim/terminal states, so a claimed-and-designed ticket reads `solution` only in the worktree.

If `$ARGUMENTS` is empty, scan `.tickets/` (not `.tickets/completed/`) for tickets with `status: solution`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before proceeding.

If no ticket is found, stop and report.

State the resolved ticket in one sentence — "Autopilot mode for XXXX-slug" — then read `${CLAUDE_PLUGIN_ROOT}/context/flows/autopilot-ticket.md` in full and follow it.
