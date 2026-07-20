# Solution

**Ticket**: 0071
**Title**: Deliver squash-merge must delete the remote ticket branch, not just the local one

## Approach

`ticket.py::_remove_branch_and_worktree` already does everything Step 4c needs
— worktree remove, local `git branch -D`, and (guarded by `_has_remote`)
`git push origin --delete branch`, non-fatal on failure. Round-1 review found
the real gap isn't the flow doc alone: `deliver_squash()` (the tested Python
function the `ticket deliver` CLI actually runs) and `deliver_squash_batch()`
both hand-roll the same worktree-remove/branch-delete pair independently, with
no remote delete, in three places total. Replace all three inline pairs with
calls to the existing helper — surgically, preserving `deliver_squash()`'s
existing fail-closed gate (cleanup only runs after `main`'s push succeeds) byte
for byte. Update `deliver-ticket.md` Step 4c's prose to document the result.

## Components

| Component | Responsibility |
|-----------|----------------|
| `ticket.py::deliver_squash` (lines 774-775) | Replace `git(repo, "worktree", "remove", ...)` + `git(repo, "branch", "-D", branch, ...)` with `_remove_branch_and_worktree(repo, slug, branch, push=True)` — same two lines, same position, still inside the `if not _push_current_branch(repo): raise RuntimeError(...)` gate above them. Nothing else in the function changes. |
| `ticket.py::deliver_squash_batch` (batch-branch site + per-member loop) | Batch-branch site: `_remove_branch_and_worktree(repo, _batch_worktree(batch_branch), batch_branch, push=True)` — the worktree lives at `.worktrees/<_batch_worktree(...)>` (slash→dash), not at a path derived from `batch_branch` literally (round-2 finding: passing `batch_branch` as the worktree-dir arg would silently orphan the real worktree). Per-member loop: each site passes its own `slug` directly for both args — no transform needed, since a member's worktree dir already equals its slug. |
| `ticket.py::_remove_branch_and_worktree` | No change — already correct, already used by `cancel`/`abandon`. |
| `context/flows/deliver-ticket.md` Step 4c | Prose updated to name the helper call, documenting the Python change — not itself the fix. |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Fix `deliver_squash`/`deliver_squash_batch` directly, not just the flow doc | Round 1: the flow-doc-only edit doesn't touch the actual tested code path the `ticket deliver` CLI runs — the bug lives in Python, not markdown. |
| Surgical two-line replacement, position preserved | Keeps the existing `if not _push_current_branch(...)` fail-closed gate intact by construction — no restructuring that could accidentally move cleanup outside it. |
| Reuse `_remove_branch_and_worktree` over a new inline `git push --delete` line | One tested implementation instead of a fourth independent hand-rolled sequence. |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-1, FR-3 | Unit (red first) | `deliver_squash`/`deliver_squash_batch` on a fixture with a remote: branch, worktree, and remote branch all gone — the batch case asserts against `.worktrees/<_batch_worktree(batch_branch)>` specifically, not a literal-`batch_branch`-derived path, so a wrong-argument implementation false-fails rather than false-passes. |
| FR-2 | Regression | `test_deliver_squash_preserves_branch_and_worktree_on_rejected_push` (line 365) passes unmodified — cleanup, including the new remote delete, never runs on a rejected `main` push. |
| FR-4 | Unit | No-remote fixture: cleanup completes, no remote-delete attempted. |
| FR-5 | Unit | Forced remote-delete failure: delivery still reports success. |
| FR-7 | Direct check | `status`/`stale`/`ticket-status` read only worktree existence, never branch existence — confirmed by inspection, no test needed. |

## Tradeoffs

- **Chose fixing 3 call sites over 1 because**: round 1 found the flow-doc-only scope missed the two Python functions the CLI actually runs; leaving `deliver_squash_batch` unfixed would recreate the same leak for every batch delivery.
- **Accepting risk of**: a still-undiscovered fourth hand-rolled cleanup site; none found in this session's `grep` for `worktree.*remove` / `branch.*-D` across `ticket.py`.

## Risks

- The rejected-push gate is the one destructive-operation invariant this ticket must not weaken — mitigated by the surgical, position-preserving replacement and the named regression test as a hard acceptance gate, not just a suite pass.

## Implementation Order

1. Write the red tests first (with-remote, no-remote, forced-failure, and confirm the existing rejected-push regression test still exists and still fails if cleanup were moved outside the gate) — TDD, before any implementation edit.
2. Replace `deliver_squash`'s two lines with the helper call, in place.
3. Replace `deliver_squash_batch`'s three sites with the helper call, in place.
4. Update `deliver-ticket.md` Step 4c's prose to match.
5. Run the full existing deliver/cancel/abandon suite to confirm no regression.
