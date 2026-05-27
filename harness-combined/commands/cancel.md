Abandon an in-flight ticket: removes the worktree, deletes the branch, and sets status to `cancelled`. Safe to run at any stage before merge.

## Ticket Resolution

If a ticket number is provided as an argument, use it. Otherwise scan `.tickets/` for tickets whose status is not `done` and not `cancelled`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. **Read `status.md`** for the resolved ticket. Extract:
   - `status` — must not be `done` or `cancelled`. If it is, tell the lead and stop.
   - `branch` — the branch name (e.g. `ticket/XXXX-<slug>`)
   - `ticket` — the four-digit number

2. **Confirm with the lead** before proceeding. Show exactly what will happen:
   ```
   Ready to cancel ticket XXXX:
     git worktree remove .worktrees/XXXX-<slug>  (if worktree exists)
     git branch -d <branch>                       (if branch exists)
     status.md → cancelled
     .tickets/.active deleted                     (if it matches this ticket)
   This cannot be undone without git reflog. Proceed? (yes/no)
   ```
   Stop if the lead says no.

3. **Remove the worktree** (if `.worktrees/XXXX-<slug>` exists).
   Run: `git worktree remove --force .worktrees/XXXX-<slug>`
   The `--force` flag is needed because the worktree may have uncommitted changes. If this fails, warn the lead and continue.

4. **Delete the branch** (if `git branch --list <branch>` shows it exists).
   Run: `git branch -D <branch>`
   Use `-D` rather than `-d` because the branch may not be merged. If this fails, warn the lead and continue.

5. **Clear the active-ticket sentinel** if `.tickets/.active` exists and contains this ticket's slug.
   Run: `rm -f .tickets/.active`

6. **Release the ticket lock** if `.tickets/.ticket.lock` exists (guards against a crash mid-claim).
   Run: `rm -f .tickets/.ticket.lock`

7. **Update ticket status.**
   Set `status.md` to `status: cancelled` and update the `updated` date.

8. **Report completion.**
   Confirm what was cleaned up and note any warnings from earlier steps. Remind the lead that the ticket directory (`.tickets/XXXX-<slug>/`) is preserved for reference — delete it manually if it is no longer needed.
