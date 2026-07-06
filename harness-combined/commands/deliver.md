Deliver `$ARGUMENTS` — merge the ticket worktree, or write a spec artifact to its target file.

If `$ARGUMENTS` is empty, ask the lead whether to deliver a ticket (give a number) or a standalone run (give a run-id, or default to the most recent passed run).

## Mode selection

Look at `$ARGUMENTS` and pick exactly one mode:

- **Ticket mode** — argument begins with four digits (e.g. `0001`, `0023-add-inventory`). A ticket directory exists at `.tickets/<arg>*/` or `.tickets/completed/<arg>*/` with `status: review-ready`.
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/deliver-ticket.md` in full and follow it.

- **Spec mode** — anything else (a run-id from `.harness/results/`, or empty meaning "the most recent passed run").
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/deliver-spec.md` in full and follow it.

State the chosen mode in one sentence **before** loading the flow file.

## The `--pr` flag

`/deliver` accepts an optional `--pr` flag anywhere in `$ARGUMENTS`. Strip it out when computing the mode-selection argument (it is not part of the ticket number or run-id), then dispatch on mode:

- **Ticket mode** — forward `--pr` to `deliver-ticket.md`: pass the flag through so that flow pushes the branch and opens a GitHub PR (Step 3.5) before the local merge. The `--pr` flag is **only** meaningful in ticket mode.
- **Spec mode** — `--pr` is **only supported in ticket mode**. When `--pr` is present in spec mode, emit a warning (`--pr is only supported in ticket mode; ignoring it`) and **continue** the normal spec deliver flow without error. Do not open a PR; a standalone run has no ticket branch or design artifacts to build a PR from.

If the argument starts with four digits but no matching ticket directory exists in either `.tickets/` or `.tickets/completed/`, ask the lead whether they meant a ticket or a standalone run-id that happens to start with digits.
