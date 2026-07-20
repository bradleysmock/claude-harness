# Requirements

**Ticket**: 0071
**Title**: Deliver squash-merge must delete the remote ticket branch, not just the local one

## Functional Requirements

1. `ticket.py::deliver_squash`'s cleanup (currently inline `git worktree
   remove` + `git branch -D`, lines 774-775) must call
   `_remove_branch_and_worktree(repo, slug, branch, push=True)` instead, adding
   the remote delete for free.
2. The replacement in FR-1 must sit inside the existing
   `if not _push_current_branch(repo): raise RuntimeError(...)` gate exactly
   where the current two lines sit — cleanup, including the new remote delete,
   only runs after `main`'s push succeeds. Never before.
3. `ticket.py::deliver_squash_batch`'s three inline cleanup sites (batch
   branch, and each member's branch/worktree) must use the same helper. The
   batch-branch call must pass `_batch_worktree(batch_branch)` — not
   `batch_branch` itself — as the helper's worktree-dir argument (`full_slug`),
   since the worktree lives at `.worktrees/<batch-slug-with-dashes>`, not at a
   path derived from the branch name's literal `/`. Each member's call passes
   its own slug directly (no transform needed there).
4. The remote delete is skipped cleanly when no remote exists, via
   `_remove_branch_and_worktree`'s existing `_has_remote(repo)` guard.
5. A failed/rejected remote-branch delete must not abort delivery or touch the
   already-published `main`/ledger state — already true of the helper's
   existing `check=False` remote-delete call; no new error-swallowing needed.
6. `context/flows/deliver-ticket.md` Step 4c's prose documents the corrected
   sequence — it is documentation of the Python change, not a substitute for it.
7. `commands/ticket-status.md`/`skills/stale/SKILL.md`/`skills/status/SKILL.md`
   must not regress — none treat branch existence as a signal.

## Non-Functional Requirements

1. No new dependencies; reuses the existing `git()` helper and argument-list style.
2. `tests/test_ticket_module.py::test_deliver_squash_preserves_branch_and_worktree_on_rejected_push`
   keeps passing unmodified — the fail-closed gate isn't weakened.

## Test Strategy

| Type       | Rationale                                                        |
|------------|--------------------------------------------------------------------|
| Unit       | `deliver_squash` on a fixture with a remote: local branch, worktree, and remote branch all gone after delivery. |
| Unit       | `deliver_squash_batch`: same, for the batch branch and every member. |
| Unit       | No-remote fixture: cleanup completes, no remote-delete attempted. |
| Unit       | Forced remote-delete failure: delivery still reports success. |
| Regression | The existing rejected-main-push test (line 365) passes unmodified — cleanup, including remote delete, never runs when `main`'s push fails. |

## Acceptance Criteria

- Delivering a ticket (solo or batch) against a fixture remote leaves no
  `origin/ticket/<slug>` branch afterward.
- A remote-delete failure is non-fatal; a rejected `main` push still leaves
  everything — including the remote branch — fully intact.
- All pre-existing tests pass unmodified.

## Open Questions

None — FR-7 is verified directly against current `status`/`stale`/`ticket-status`
logic (none reads branch existence), independent of ticket 0070's delivery order.
