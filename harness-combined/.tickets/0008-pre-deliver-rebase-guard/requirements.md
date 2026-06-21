# Requirements

**Ticket**: 0008
**Title**: Pre-deliver rebase guard

## Functional Requirements

1. The system must, after Step 1 validation and before Step 3 confirmation (as new Step 2b), check whether the ticket branch's divergence count from the delivery target (default: `main`) is zero, using `git rev-list --count <target>...<branch>`.
2. The system must report divergence in the form: "Warning: branch is N commit(s) behind <target>. Pass --rebase to auto-rebase before delivering, or rebase manually."
3. The system must halt the delivery flow if divergence is detected and `--rebase` was not passed.
4. The system must validate the delivery target branch name against `^[a-zA-Z0-9][a-zA-Z0-9/_.-]*$` before passing it to any git command; halt with a named error if validation fails.
5. The system must, when `--rebase` is passed and divergence is detected, check that the worktree is not already in a mid-rebase state before executing `git rebase <target>`; halt with a named error if mid-rebase state is detected.
6. The system must, when `--rebase` is passed and rebase succeeds, pass a gate-invalidation notice to the Step 3 confirmation block.
7. The system must abort and report failure if the auto-rebase encounters conflicts: call `git rebase --abort` as a checked sub-step; if the abort itself fails, report both errors and instruct the operator to clean up manually. In all conflict cases, do not proceed to Step 3.
8. The system must proceed without interruption when the branch is already up to date with the target.
9. The system must surface the divergence check result in the Step 3 confirmation block when delivery proceeds (branch up to date, or `--rebase` succeeded). The Step 3 block is not reached when delivery halts at Step 2b; the halt path is covered by FR-3.

## Non-Functional Requirements

1. The divergence check must use only local git state — no network calls.
2. The divergence check must complete in under one second on commit-graph-enabled repos (`.git/objects/info/commit-graph` present).

## Test Strategy

| Type        | Rationale                                                                 |
|-------------|---------------------------------------------------------------------------|
| Unit        | Test divergence-count logic: up-to-date branch returns 0; behind by N returns N |
| Integration | `--rebase` success: rebase executes, delivery continues, gate-invalidation notice appears in Step 3 prompt; `--rebase` conflict: `git rebase --abort` is called, delivery halts cleanly; mid-rebase guard: halt if worktree already mid-rebase; abort-failure: both errors reported |

## Acceptance Criteria

- Delivering a branch 0 commits behind the target produces no warning and proceeds normally.
- Delivering a branch N > 0 commits behind the target without `--rebase` prints the warning and halts before Step 3.
- Delivering with `--rebase` when N > 0 rebases the branch and continues to the Step 3 confirmation prompt, which includes the gate-invalidation notice.
- If `--rebase` triggers a conflict, `git rebase --abort` is called as a checked step; the command reports the conflict and halts without touching the target branch.
- If `git rebase --abort` itself fails, both errors are reported and the operator is instructed to clean up manually.
- When delivery proceeds to Step 3 (up-to-date or successful rebase), the confirmation block states the branch status.
- An invalid branch name in `status.md` halts delivery before any git command runs.
- A worktree already in mid-rebase state halts delivery with a named error when `--rebase` is passed.

## Open Questions

- None.
