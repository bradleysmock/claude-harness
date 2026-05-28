Build `$ARGUMENTS` — generate, validate, and write the implementation.

If `$ARGUMENTS` is empty, ask the lead which ticket or spec to build before doing anything else.

## Mode selection

Look at `$ARGUMENTS` and pick exactly one mode:

- **Ticket mode** — argument begins with four digits (e.g. `0001`, `0023-add-inventory`). A ticket directory exists at `.tickets/<arg>*/` with a `solution.md` and one or more specs at `.harness/specs/<arg>*.py`.
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/build-ticket.md` in full and follow it.

- **Spec mode** — anything else (a bare spec-id or task-id under `.harness/specs/<id>.py` or `.harness/tasks/<id>.py`). No ticket, no worktree.
  → Read `${CLAUDE_PLUGIN_ROOT}/context/flows/build-spec.md` in full and follow it.

State the chosen mode in one sentence ("ticket mode for 0023-add-inventory" / "spec mode for auth-login") **before** loading the flow file.

If the argument is ambiguous (e.g. four-digit prefix but no matching ticket directory, or a name that looks like a spec but also matches a ticket slug), tell the user what you found and ask which mode they intended.
