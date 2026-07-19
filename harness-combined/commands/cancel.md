Cancel an in-flight ticket: removes the worktree, deletes the branch, appends a `cancelled` lifecycle event to the `harness-tickets` ledger, and archives the ticket docs **onto `harness-tickets`** (under `cancelled/XXXX-<slug>/`). This path is **main-free** — a cancelled ticket never merged, so nothing about it lands on `main`. Safe to run at any stage before merge.

With `--abandon`, the terminal event is `abandoned` instead of `cancelled` — use it when work was started but dropped rather than deliberately cancelled. (`/abandon` is the dedicated alias for this path.)

## Ticket Resolution

If a ticket number is provided as an argument, resolve it from the `harness-tickets` ledger's `claim` events (and its worktree `.worktrees/<arg>*/` for the live status). Otherwise list in-flight tickets — a `claim` in the ledger with no terminal (`delivered`/`cancelled`/`abandoned`) event — and, if exactly one exists, use it; if multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. **Read the live `status.md`** for the resolved ticket from its worktree (`.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/status.md`). Extract:
   - `status` — must not be `done` or `cancelled` (nor `abandoned`). If it is, tell the lead and stop.
   - `branch` — the branch name (e.g. `ticket/XXXX-<slug>`)
   - `ticket` — the four-digit number

2. **Confirm with the lead** before proceeding. Show exactly what will happen:
   ```
   Ready to cancel ticket XXXX (main-free — nothing touches main):
     append {"event":"cancelled","number":XXXX} to the harness-tickets ledger (pushed)
     archive the ticket docs onto harness-tickets under cancelled/XXXX-<slug>/
     git worktree remove .worktrees/XXXX-<slug>  (if worktree exists)
     git branch -D <branch>                       (local + origin, if it exists)
     .tickets/.active deleted                     (if it matches this ticket)
   This cannot be undone without git reflog. Proceed? (yes/no)
   ```
   Stop if the lead says no.

3. **Clear the active-ticket sentinel** if `.tickets/.active` exists and contains this ticket's slug: `rm -f .tickets/.active`.

4. **Release the ticket lock** if `.tickets/.ticket.lock` exists (guards against a crash mid-claim): `rm -f .tickets/.ticket.lock`.

5. **Cancel via the helper** — one main-free transaction. It appends the `cancelled` ledger event (pushed first-wins, honoring the §1a push invariant), snapshots the ticket docs onto `harness-tickets` (so `/reopen` can restore them), and removes the worktree + branch (local and `origin`). Under `--abandon`, use `abandon`:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" cancel XXXX --push
   # or, for the abandoned path:
   python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" abandon XXXX --push
   ```

   **Idempotency:** the helper is idempotent by `(event, number)` — if the ledger already carries a `cancelled` (or `abandoned`) event for this number it appends nothing and simply completes the branch/worktree cleanup.

   **Partial-cleanup guard:** if the worktree or branch was already partially removed, the helper's removals are best-effort (`--force`) and will not error out; it always finishes by ensuring both are gone.

6. **Report completion.**
   Confirm what was cleaned up (worktree, branch removed local+origin, docs archived onto `harness-tickets`), note that **no `main` commit was made**, and remind the lead that `/reopen XXXX` restores the ticket from its `harness-tickets` archive onto a fresh branch.
