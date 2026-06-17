Move an archived ticket from `.tickets/completed/` back to `.tickets/` root and set its status to `solution`. Only tickets with status `done` or `cancelled` in `.tickets/completed/` are eligible.

## Ticket Resolution

If a ticket number is provided as an argument, scan `.tickets/completed/<arg>*/`. If not found there, check `.tickets/<arg>*/` — if the ticket is already at root and its status is active, tell the lead it is not archived and stop. Otherwise scan `.tickets/completed/` for all tickets with status `done` or `cancelled`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. **Read `status.md`** for the resolved ticket. Extract:
   - `status` — must be `done` or `cancelled`. If it is any other value, tell the lead and stop.
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
     mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/
     status.md → solution
     git rm -r --cached .tickets/completed/XXXX-<slug>/
     git add -- .tickets/XXXX-<slug>/
     git commit -m "chore(ticket): XXXX → solution (reopened)"
   Re-run /build XXXX before resuming work. Proceed? (yes/no)
   ```
   Stop if the lead says no.

4. **Move the ticket back to root.**
   ```
   mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/
   ```
   If the mv fails, report the error and stop.

5. **Update ticket status.**
   Set `status.md` to `status: solution` and update the `updated` date.

6. **Commit the reopen transition** (see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):
   ```
   git rm -r --cached .tickets/completed/XXXX-<slug>/
   git add -- .tickets/XXXX-<slug>/
   git commit -m "chore(ticket): XXXX → solution (reopened)"
   ```

7. **Report completion.**
   Confirm the ticket is now at `.tickets/XXXX-<slug>/` with `status: solution`. Remind the lead:
   - Run `/build XXXX` before resuming implementation — existing specs may be stale.
   - The original branch and worktree were deleted at cancel/deliver time; `/build` will create a new branch and worktree.
