---
description: Move an archived ticket from .tickets/completed/ back to .tickets/ root and set its status
---
Move an archived ticket from `.tickets/completed/` back to `.tickets/` root and set its status to `solution`. Only tickets with status `done`, `cancelled`, or `abandoned` in `.tickets/completed/` are eligible.

## Ticket Resolution

If a ticket number is provided as an argument, scan `.tickets/completed/<arg>*/`. If not found there, check `.tickets/<arg>*/` — if the ticket is already at root and its status is active, tell the lead it is not archived and stop. Otherwise scan `.tickets/completed/` for all tickets with status `done`, `cancelled`, or `abandoned`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. **Read `status.md`** for the resolved ticket. Extract:
   - `status` — must be `done`, `cancelled`, or `abandoned`. If it is any other value, tell the lead and stop.
   - `ticket` — the four-digit number
   - `slug` — the full `XXXX-<slug>` directory name

2. **Check for partial-move-back state.**
   If `.tickets/XXXX-<slug>/` already exists at root, warn the lead:
   ```
   Warning: .tickets/XXXX-<slug>/ already exists at root. Partial-move-back state detected.
   Root copy is treated as authoritative. Verify its contents and run /build XXXX to resume.
   ```
   Stop — do not overwrite.

3. **Confirm with the lead** before proceeding:
   ```
   Ready to reopen ticket XXXX:
     git worktree add .worktrees/XXXX-<slug> -b ticket/XXXX-<slug> main   (fresh branch from main HEAD)
     mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/   (in the worktree)
     status.md → solution
     git rm -r --cached .tickets/completed/XXXX-<slug>/
     git add -- .tickets/XXXX-<slug>/
     git commit -m "chore(ticket): XXXX → solution (reopened)"   (on the branch, then push)
   Re-run /build XXXX before resuming work. Proceed? (yes/no)
   ```
   Stop if the lead says no.

4. **Fork a fresh branch + worktree from `main` HEAD.**
   The prior delivery squash-merged **and deleted** the original `ticket/XXXX-<slug>` branch, so its per-commit history is gone — the squashed commit on `main` is the new base. Fork a fresh branch from `main` HEAD and check it out in a worktree:
   ```
   git worktree add .worktrees/XXXX-<slug> -b ticket/XXXX-<slug> main
   ```
   If the branch already exists (a stale leftover), pick it up instead: `git worktree add .worktrees/XXXX-<slug> ticket/XXXX-<slug>`. If worktree creation fails, report and stop.

5. **Restore the ticket dir onto the branch.** All of the following happen **in the worktree** (`.worktrees/XXXX-<slug>/`), committed on the branch — never on `main`. `main` keeps the archived `completed/XXXX-<slug>/` until the next `/deliver` squash.
   ```
   mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/
   ```
   If the mv fails, report the error and stop.

6. **Set status and commit the reopen transition on the branch** (see "Committing ticket metadata" in `/Users/bradley/workspaces/claude-harness/harness-combined/context/harness-reference.md`). Set `status.md` to `status: solution` with an updated date, then:
   ```
   git -C .worktrees/XXXX-<slug> rm -r --cached .tickets/completed/XXXX-<slug>/
   git -C .worktrees/XXXX-<slug> add -- .tickets/XXXX-<slug>/
   git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → solution (reopened)"
   git -C .worktrees/XXXX-<slug> push
   ```

7. **Report completion.**
   Confirm the ticket dir is restored at `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/` with `status: solution` on the fresh branch. Remind the lead:
   - Run `/build XXXX` before resuming implementation — existing specs may be stale; `/build` resumes this worktree.
   - The next `/deliver` squashes the reopened work into a **further** commit on `main`.
