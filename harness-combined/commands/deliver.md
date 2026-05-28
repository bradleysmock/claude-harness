Deliver `$ARGUMENTS` — merge the ticket worktree, or write a spec artifact to its target file.

If `$ARGUMENTS` is empty, ask the lead whether to deliver a ticket (give a number) or a standalone run (give a run-id, or default to the most recent passed run).

## Mode selection

Look at `$ARGUMENTS` and pick exactly one mode:

- **Ticket mode** — argument begins with four digits (e.g. `0001`, `0023-add-inventory`). A ticket directory exists at `.tickets/<arg>*/` with `status: review-ready`.
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/deliver-ticket.md` in full and follow it.

- **Spec mode** — anything else (a run-id from `.harness/results/`, or empty meaning "the most recent passed run").
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/deliver-spec.md` in full and follow it.

State the chosen mode in one sentence **before** loading the flow file.

If the argument starts with four digits but no matching ticket directory exists, ask the lead whether they meant a ticket or a standalone run-id that happens to start with digits.
