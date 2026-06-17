Build `$ARGUMENTS` — generate, validate, and write the implementation.

If `$ARGUMENTS` is empty, ask the lead which ticket or spec to build before doing anything else.

## Mode selection

Look at `$ARGUMENTS` and pick exactly one mode:

- **Ticket mode** — argument begins with four digits (e.g. `0001`, `0023-add-inventory`). A ticket directory exists at `.tickets/<arg>*/` or `.tickets/completed/<arg>*/` with an approved `solution.md`. Specs need not exist yet — `/build` generates them from `solution.md` if absent (the optional `/write-spec XXXX` can pre-generate or hand-tune them first).
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/build-ticket.md` in full and follow it.

- **Spec mode** — anything else: a bare spec-id/task-id under `.harness/specs/<id>.py` / `.harness/tasks/<id>.py`, or a free-form description. A description with no matching spec file makes `/build` generate the spec first. No ticket, no worktree.
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/build-spec.md` in full and follow it.

State the chosen mode in one sentence ("ticket mode for 0023-add-inventory" / "spec mode for auth-login") **before** loading the flow file.

If the argument is ambiguous (e.g. four-digit prefix but no matching ticket directory in either `.tickets/` or `.tickets/completed/`, or a name that looks like a spec but also matches a ticket slug), tell the user what you found and ask which mode they intended.
