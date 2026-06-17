Write spec(s) for `$ARGUMENTS`.

If `$ARGUMENTS` is empty, ask the lead what to spec — a ticket number, or a free-form description — before doing anything else.

## Mode selection

Look at `$ARGUMENTS` and pick exactly one mode:

- **Ticket mode** — argument begins with four digits (e.g. `0001`, `0023-add-inventory`). A ticket directory exists at `.tickets/<arg>*/` or `.tickets/completed/<arg>*/` with `status: solution`. The design phase already explored the codebase, so do **not** re-explore.
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/write-spec-ticket.md` in full and follow it.

- **Spec mode** — anything else (a free-form description like "add bulk-export endpoint" or "refactor auth session store"). No ticket involved. The codebase must be explored before writing a spec.
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/write-spec-spec.md` in full and follow it.

State the chosen mode in one sentence **before** loading the flow file.

If the argument starts with four digits but no matching ticket directory exists in either `.tickets/` or `.tickets/completed/`, ask the lead whether they meant a ticket (and forgot to run `/problem` first) or a free-form description that happens to start with digits.
