# Problem Statement

**Ticket**: 0008
**Title**: Pre-deliver rebase guard
**Date**: 2026-06-21

## Problem

The `/deliver` command merges a ticket branch into the target branch (typically `main`) without first verifying that the ticket branch is up to date with its base. If `main` has advanced since the gate suite ran, the delivery merge may introduce conflicts or regression — after the gates have already passed on a stale baseline. This is the same class of gap GitHub branch protection closes with "require branch to be up to date before merging."

## Impact

- The harness operator is affected: a delivery that looked gate-clean can produce a broken `main`.
- Silent divergence means the operator has no visibility into how stale the branch is before committing to a merge.
- Without a guard, post-delivery conflict resolution happens on `main` rather than on the ticket branch where gates can re-run.

## Success Criteria

- Before any merge, `/deliver` detects whether `main` (or the configured target) has commits not present in the ticket branch.
- If diverged, the command prints a clear warning showing the number of commits behind.
- A `--rebase` flag automatically rebases the ticket branch onto the current target before merging.
- If the branch is already up to date, delivery proceeds without any additional user interaction.
- No gate-passing delivery is silently allowed on a stale branch.

## Out of Scope

- Re-running the full gate suite automatically after a rebase (that is a separate concern).
- Divergence detection for branches other than the configured delivery target.
- Conflict resolution assistance (the guard detects and halts; the operator resolves).
