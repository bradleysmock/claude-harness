# Problem Statement

**Ticket**: 0033
**Title**: Replan command
**Date**: 2026-06-21

## Problem

Once a ticket has been designed and work begins, requirements often shift — the lead edits `requirements.md` after initial design, or `/build` uncovers scope changes that need to be documented. There is currently no supported path to re-run solution planning on an already-speced ticket without manually editing artifacts and re-running the critic. This leaves the ticket's `solution.md` stale relative to the actual requirements, silently breaking the design contract.

## Impact

- Harness operators (lead engineers) are forced to hand-edit `solution.md` when requirements change, with no critic loop or diff visibility.
- Stale `solution.md` artifacts mislead the `/build` pipeline, causing implementation to diverge from current requirements.
- Scope changes discovered during `/build` cannot be documented cleanly without a dedicated replanning workflow.

## Success Criteria

- A `/replan XXXX` command accepts a ticket number and re-derives `solution.md` from the current `problem.md` and `requirements.md`.
- The command runs the full critic loop (up to 2 rounds) on the regenerated solution.
- After the critic loop, a unified diff of the old vs. new `solution.md` is presented to the lead.
- Ticket `status.md` is updated and the revised artifacts are committed.
- The command is a no-op if `requirements.md` has not changed since the last solution commit (or proceeds with a warning — see Open Questions).

## Out of Scope

- Modifying `problem.md` as part of replanning (only `requirements.md` and `solution.md` are in scope).
- Re-running `/write-spec` or regenerating gate specs automatically after replanning.
- Merging or reconciling in-progress worktree changes with the new solution.
