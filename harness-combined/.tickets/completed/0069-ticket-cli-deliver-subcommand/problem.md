# Problem Statement

**Ticket**: 0069
**Title**: Ticket CLI deliver subcommand
**Date**: 2026-07-19

## Problem

`ticket.py`'s CLI dispatch (`_main()`) wires up `owner`, `set-status`, `claim`,
`deliver-batch`, `ensure-branch`, `migrate`, `next-number`, `list-json`,
`cancel`, `abandon`, and `reopen` — but has no `deliver` case for a single
ticket, even though `deliver_squash(repo, branch, slug, title)` already
exists and is fully implemented (pushes `main`, folds the archive, appends
the `delivered` ledger event, removes the worktree, deletes the branch).

## Impact

- The documented single-ticket delivery flow (`context/flows/deliver-ticket.md`
  Step 4) has no CLI command to invoke — only literal git commands plus an
  in-process call to `deliver_squash()` exist as the operational path.
- Anyone delivering a single ticket outside a full `/deliver` session (a
  script, CI, or an agent operating headless) has no supported entry point
  and must reach into `ticket.py` internals via `python3 -c "..."`.
- `deliver_squash()` is exercised by unit tests but has no CLI-level
  integration test, unlike `deliver-batch`, which is both CLI-wired and
  presumably covered end-to-end via its subcommand.

## Success Criteria

- `ticket.py deliver <ticket-id> [--push]` (or an equivalently named
  subcommand) invokes `deliver_squash()` for a single ticket and prints its
  result, mirroring the `deliver-batch` case's shape.
- Errors from `deliver_squash()` (rejected push, squash-merge conflict) are
  reported as non-zero exit with the underlying message, not swallowed.
- The new subcommand is covered by tests at the CLI-dispatch level (not just
  `deliver_squash()` itself, which is already tested).

## Out of Scope

- Changing `deliver_squash()`'s internal behavior, signature, or the
  `deliver-batch` subcommand.
- Rewiring `context/flows/deliver-ticket.md` to invoke the new subcommand
  instead of its literal git-command sequence (a documentation follow-up,
  not required for the CLI gap itself).
