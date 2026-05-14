Merge an approved ticket branch into main and clean up the worktree.

## Ticket Resolution

If a ticket number is provided as an argument, use it. Otherwise scan `.tickets/` for tickets with `status: review-ready`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. **Read `status.md`** for the resolved ticket. Extract:
   - `branch` — the branch name (e.g. `ticket/0001-slug`)
   - `ticket` — the four-digit number (e.g. `0001`)

2. **Validate preconditions.**
   - Confirm `status` is `review-ready`. If not, tell the lead the ticket is not approved for merge and stop.
   - Run `git branch --list <branch>` to confirm the branch exists. If it doesn't, tell the lead and stop.
   - Check that the worktree directory `.worktrees/XXXX-<slug>` exists. If it doesn't, note it and continue (may have been removed manually).
   - Run `git status` to confirm the main repo working tree is clean. If there are uncommitted changes, warn the lead and stop.

3. **Check for file-level conflicts with other review-ready tickets.**
   - Get the files changed in this branch: `git diff --name-only main....<branch>`
   - Scan `.tickets/` for any other tickets with `status: review-ready`. For each, get their changed files the same way.
   - If any files overlap, report them to the lead before the confirmation step:
     ```
     Warning: the following files are also changed in other review-ready tickets:
       <file> — also in ticket YYYY (<branch>)
     Merging in the wrong order may produce conflicts.
     Suggested merge order: <reasoning based on which ticket's changes are more foundational>
     ```
   - This is a warning, not a stop. The lead decides whether to proceed.

4. **Confirm with the lead** before proceeding. Show exactly what will happen:
   ```
   Ready to merge ticket XXXX:
     git merge --no-ff <branch>
     git worktree remove .worktrees/XXXX-<slug>  (if worktree exists)
     git branch -d <branch>
     status.md → done
   Proceed? (yes/no)
   ```
   Stop if the lead says no.

5. **Merge the branch.**
   Run: `git merge --no-ff <branch>`
   If the merge fails (conflicts or other error), report the error, tell the lead to resolve it manually, and stop without continuing to cleanup.

6. **Remove the worktree** (if it exists).
   Run: `git worktree remove .worktrees/XXXX-<slug>`
   If this fails, warn the lead but continue.

7. **Delete the branch.**
   Run: `git branch -d <branch>`
   If this fails, warn the lead and do not force-delete.

8. **Update ticket status.**
   Set `status.md` to `status: done` and update the `updated` date.

9a. **Rebase in-flight worktrees onto the updated main.**

    Scan `.tickets/` for every ticket whose `status` is not `done` and whose ticket number is not XXXX (the ticket just merged). For each:

    1. Read its `status.md` to get `branch` (e.g. `ticket/YYYY-<slug>`).
    2. If `branch` is empty or stripping the `ticket/` prefix yields an empty slug, skip the entry silently (guards against malformed `status.md` files that could otherwise cause a rebase to run against the main repo, violating NFR-2).
    3. Derive the worktree path: strip the `ticket/` prefix → `.worktrees/YYYY-<slug>`.
    4. If the directory does not exist, skip it silently (FR-6).
    5. Check for a mid-rebase state using `git -C <worktree-path> rev-parse --git-dir` to locate the real gitdir, then test whether `<gitdir>/rebase-merge/` exists or `<gitdir>/REBASE_HEAD` exists.
       - If mid-rebase: record a warning — "YYYY (branch): already in a conflicted/mid-rebase state — skipped. To abort: `git -C <worktree-path> rebase --abort`" — and continue to the next ticket.
    6. Attempt: `git -C <worktree-path> rebase main`
       - **Success**: record "YYYY (branch): rebased OK".
       - **Failure**: run `git -C <worktree-path> rebase --abort` to leave the worktree clean, then record:
         ```
         YYYY (branch): REBASE FAILED — resolve conflicts manually
           Abort:  git -C <worktree-path> rebase --abort
           Retry:  git -C <worktree-path> rebase main
         ```
       - Always continue to the next ticket regardless of outcome (NFR-1).

    If no in-flight worktrees were found or all were skipped, produce no output for this step (FR-7).

9. **Report completion.**
   Summarize what was done. Note any warnings from earlier steps.

   If step 9a produced any rebase results, append a **Worktree rebase summary** section:
   ```
   ## Worktree rebase summary
   <one line per in-flight worktree: "YYYY (branch): rebased OK" or failure/warning text>
   ```
