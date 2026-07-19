Mark an in-flight ticket as `abandoned` — work was started but dropped (distinct from `cancelled`, which means a deliberate decision not to do the work). Frees the ticket for someone else to `/reopen`. This is `/cancel --abandon` with a dedicated, memorable name. Like `/cancel`, it is **main-free**: an abandoned ticket never merged, so nothing about it lands on `main` — the terminal signal is an `abandoned` event on the `harness-tickets` ledger.

## Ticket Resolution

If a ticket number is provided, resolve it from the `harness-tickets` ledger's `claim` events and its worktree. Otherwise list in-flight tickets whose live status is `implementing`; if exactly one, use it, else list them and require the lead to choose.

## Steps

1. **Read the live `status.md`** from the worktree (`.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/status.md`). The status should be `implementing` (work was started but dropped). If it is `done`, `cancelled`, or `abandoned`, tell the lead and stop.

2. **Confirm with the lead.** Show what will happen (main-free): an `abandoned` event is appended to the `harness-tickets` ledger and pushed, the ticket docs are archived onto `harness-tickets` under `abandoned/XXXX-<slug>/`, the worktree is removed, the branch deleted (local + origin), and the `.active` sentinel cleared if it matches. Stop if the lead declines.

3. **Clear sentinels:** `rm -f .tickets/.active` (if it names this ticket) and `rm -f .tickets/.ticket.lock`.

4. **Abandon via the helper** — one main-free transaction (ledger `abandoned` event pushed first-wins, docs archived onto `harness-tickets`, worktree + branch removed local and origin):

   `python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" abandon XXXX --push`

   Idempotent by `(event, number)` — a second run appends nothing and only finishes cleanup.

5. **Report completion.** Note that **no `main` commit was made**, the docs are archived on `harness-tickets`, and that `/reopen XXXX` restores the ticket onto a fresh branch.
