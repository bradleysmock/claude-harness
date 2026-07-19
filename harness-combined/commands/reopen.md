Reopen a terminal ticket onto a fresh branch forked from `main` HEAD and set its status to `solution`. Eligible tickets are those with a terminal event on the `harness-tickets` ledger — `delivered`, `cancelled`, or `abandoned`. The ticket dir is restored from its archive: `main`'s `.tickets/completed/XXXX-<slug>/` for a **delivered** ticket, or the `harness-tickets` `cancelled/`/`abandoned/XXXX-<slug>/` archive for a **cancelled/abandoned** one.

## Ticket Resolution

If a ticket number is provided as an argument, resolve it from the `harness-tickets` ledger's `claim` events. Confirm it carries a terminal event (`delivered`/`cancelled`/`abandoned`) and no later `reopened`/`claim` re-activation. If it has no terminal event it is still in-flight — tell the lead it is not archived and stop. Otherwise list all tickets whose latest ledger event is terminal; if exactly one, use it, else list them and require the lead to choose.

## Steps

1. **Read the archived `status.md`** for the resolved ticket (`main`'s `.tickets/completed/XXXX-<slug>/status.md` for a delivered ticket, else the `harness-tickets` archive). Extract:
   - `status` — must be `done`, `cancelled`, or `abandoned`. If it is any other value, tell the lead and stop.
   - `ticket` — the four-digit number
   - `slug` — the full `XXXX-<slug>` directory name

2. **Check for partial-reopen state.**
   If `.worktrees/XXXX-<slug>/` already exists at root, warn the lead:
   ```
   Warning: .worktrees/XXXX-<slug>/ already exists at root. Partial-reopen state detected.
   The existing worktree is treated as authoritative. Verify its contents and run /build XXXX to resume.
   ```
   Stop — do not overwrite.

3. **Confirm with the lead** before proceeding:
   ```
   Ready to reopen ticket XXXX onto a fresh branch from main HEAD:
     git worktree add .worktrees/XXXX-<slug> -b ticket/XXXX-<slug> main
     restore the ticket dir from its archive (main's completed/, or harness-tickets)
     status.md → solution   (committed on the branch, then pushed)
     append {"event":"reopened","number":XXXX} to the harness-tickets ledger
   Re-run /build XXXX before resuming work. Proceed? (yes/no)
   ```
   Stop if the lead says no.

4. **Reopen via the helper** — one transaction. It forks `ticket/XXXX-<slug>` from `main` HEAD into a worktree, restores the ticket dir from its archive (`main`'s `completed/` for a delivered ticket via `git rm -r --cached` + `git add`, else the `harness-tickets` archive), sets `status: solution` on the branch, pushes it, and appends a `reopened` ledger event:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" reopen XXXX --push
   ```
   `main` keeps the delivered `completed/XXXX-<slug>/` archive until the next `/deliver` squash; reopening never touches `main`.

5. **Report completion.**
   Confirm the ticket dir is restored at `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/` with `status: solution` on the fresh branch. Remind the lead:
   - Run `/build XXXX` before resuming implementation — existing specs may be stale; `/build` resumes this worktree.
   - The next `/deliver` squashes the reopened work into a **further** commit on `main`.
