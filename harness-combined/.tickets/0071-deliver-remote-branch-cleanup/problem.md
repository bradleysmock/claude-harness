# Problem Statement

**Ticket**: 0071
**Title**: Deliver squash-merge must delete the remote ticket branch, not just the local one
**Date**: 2026-07-20

## Problem

`deliver-ticket.md` Step 4c publishes `main`, then runs `git worktree remove` and
local `git branch -D <branch>` — but never `git push origin --delete <branch>`.
Every squash-delivered ticket therefore leaves its now-fully-merged branch
sitting on `origin` forever. Confirmed today: a branch review found 6 stale
remote branches (0053, 0054, 0056, 0057, 0058, 0069) whose content was already
merged into `main`, none reachable from any local branch — all had to be
deleted by hand. `ticket.py::_remove_branch_and_worktree` (used by
`cancel`/`abandon`) already does exactly this correctly — `git push origin
--delete branch` when a remote exists — deliver's Step 4c just doesn't reuse it.

## Impact

`origin`'s branch list accumulates dead branches indefinitely, one per
delivered ticket. Nothing else breaks (the branches are inert), but they add
noise to `git branch -r`, GitHub's branch picker, and any future branch audit —
this cleanup otherwise recurs by hand forever.

## Success Criteria

- `deliver-ticket.md` Step 4c deletes the remote branch (`git push origin
  --delete <branch>`) as part of the same publish-then-cleanup sequence that
  already removes the worktree and deletes the local branch.
- A rejected/failed remote delete does not abort delivery — `main` is already
  published and durable by that point; a remote-branch-delete failure is
  reported, not fatal.
- Ticket-list/status tooling is unaffected (branches were never their source of
  truth — the ledger and `.tickets/completed/` are).

## Out of Scope

- `/cancel`/`/abandon` — already correct; the pattern this ticket reuses.
- Auto-cleaning the 6 branches already found — deleted by hand today.
