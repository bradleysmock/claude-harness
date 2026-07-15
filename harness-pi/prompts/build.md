---
description: Build $ARGUMENTS — generate, validate, and write the implementation.
---
Build `$ARGUMENTS` — generate, validate, and write the implementation.

If `$ARGUMENTS` is empty, ask the lead which ticket or spec to build before doing anything else.

## `--dry-run` flag

Before mode selection, strip a `--dry-run` flag from `$ARGUMENTS` if present (it may appear anywhere in the argument string; the helper `parse_dry_run_flag` in `dry_run.py` does this and returns the remaining argument). A dry run previews a build — it runs every gate phase and the critic in full and prints a plan of the files a live build *would* write, but writes **no** implementation files, creates **no** worktree, and leaves `status.md` untouched.

- **`--dry-run` is ticket mode only.** If the surviving argument does not begin with four digits (i.e. it would select spec mode), reject with an error and stop — `validate_dry_run_mode` raises `DryRunModeError` for this case. Do not fall through to a normal build.
- When `--dry-run` is present and the surviving argument is a ticket, announce "dry-run ticket mode for XXXX-slug" and read `/Users/bradley/workspaces/claude-harness/harness-combined/context/flows/build-dry-run-ticket.md` in full and follow it instead of `build-ticket.md`.
- When `--dry-run` is absent, continue to normal mode selection below with the (unchanged) argument.

## Mode selection

Look at `$ARGUMENTS` and pick exactly one mode:

- **Ticket mode** — argument begins with four digits (e.g. `0001`, `0023-add-inventory`). A ticket directory exists at `.tickets/<arg>*/` or `.tickets/completed/<arg>*/` with an approved `solution.md`. Specs need not exist yet — `/build` generates them from `solution.md` if absent (the optional `/write-spec XXXX` can pre-generate or hand-tune them first).
  → Read `/Users/bradley/workspaces/claude-harness/harness-combined/context/flows/build-ticket.md` in full and follow it.

- **Spec mode** — anything else: a bare spec-id/task-id under `.harness/specs/<id>.py` / `.harness/tasks/<id>.py`, or a free-form description. A description with no matching spec file makes `/build` generate the spec first. No ticket, no worktree.
  → Read `/Users/bradley/workspaces/claude-harness/harness-combined/context/flows/build-spec.md` in full and follow it.

State the chosen mode in one sentence ("ticket mode for 0023-add-inventory" / "spec mode for auth-login") **before** loading the flow file.

If the argument is ambiguous (e.g. four-digit prefix but no matching ticket directory in either `.tickets/` or `.tickets/completed/`, or a name that looks like a spec but also matches a ticket slug), tell the user what you found and ask which mode they intended.
