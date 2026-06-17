Abandon an in-flight ticket: removes the worktree, deletes the branch, sets status to `cancelled`, and archives the ticket to `.tickets/completed/`. Safe to run at any stage before merge.

## Ticket Resolution

If a ticket number is provided as an argument, scan `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/` if not found there. Otherwise scan `.tickets/` for tickets whose status is not `done` and not `cancelled`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

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
     mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/   (archive)
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

   Commit the metadata transition to `main` (scoped add — see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):
   ```
   git add .tickets/XXXX-<slug>/
   git commit -m "chore(ticket): XXXX → cancelled"
   ```

8. **Archive the ticket directory.**
   Move the ticket out of the active root into the completed subfolder:
   ```
   mkdir -p .tickets/completed
   mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/
   git rm -r --cached .tickets/XXXX-<slug>/
   git add -- .tickets/completed/XXXX-<slug>/
   git commit -m "chore(ticket): XXXX archive → completed/"
   ```
   This is always a **separate commit** from Step 7 — never amend, as Step 7 may already be pushed.

   **Idempotency:** If `.tickets/completed/XXXX-<slug>/` already exists and `.tickets/XXXX-<slug>/` is absent, skip the mv and git operations (already archived) and continue.

   **Partial-move guard:** If both `.tickets/XXXX-<slug>/` and `.tickets/completed/XXXX-<slug>/` exist simultaneously, warn the lead — treat the root copy as authoritative and proceed with the mv from root.

9. **Report completion.**
   Confirm what was cleaned up (worktree, branch, archive location), note any warnings from earlier steps, and remind the lead that the ticket is now in `.tickets/completed/XXXX-<slug>/`. Use `/reopen XXXX` to resume work on it.
