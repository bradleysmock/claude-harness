Mark an in-flight ticket as `abandoned` — work was started but dropped (distinct from `cancelled`, which means a deliberate decision not to do the work). Frees the ticket for someone else to `/reopen` and signals on `main` that no one is actively driving it. This is `/cancel --abandon` with a dedicated, memorable name.

## Ticket Resolution

If a ticket number is provided, scan `.tickets/<arg>*/` then `.tickets/completed/<arg>*/`. Otherwise scan `.tickets/` for tickets whose status is `implementing`; if exactly one, use it, else list them and require the lead to choose.

## Steps

1. **Read `status.md`.** The status should be `implementing` (work was started but dropped). If it is `done`, `cancelled`, or `abandoned`, tell the lead and stop.

2. **Confirm with the lead.** Show what will happen: the worktree (if any) is removed, the branch deleted, status.md → abandoned, the `.active` sentinel cleared if it matches, and the ticket archived to `.tickets/completed/`. Stop if the lead declines.

3. **Remove the worktree** if `.worktrees/XXXX-<slug>` exists: `git worktree remove --force .worktrees/XXXX-<slug>`. The worktree exists from **claim time** for any ticket past claim. Warn and continue on failure.

4. **Delete the branch** if it exists: `git branch -D ticket/XXXX-<slug>`. The branch also exists from claim time and is unmerged, so use `-D`. Warn and continue on failure.

5. **Clear sentinels:** `rm -f .tickets/.active` (if it names this ticket) and `rm -f .tickets/.ticket.lock`.

6. **Set status to abandoned** with the helper (atomic edit + scoped commit + push):

   `python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX abandoned --push`

7. **Archive the ticket directory** to `.tickets/completed/` using the same mv + `git rm -r --cached` + `git add -- .tickets/completed/XXXX-<slug>/` + commit pattern as `/cancel` Step 8, then `git push`. Apply the same **Idempotency** and **Partial-move guard** rules. This is always a separate commit.

8. **Report completion.** Note the archive location and that `/reopen XXXX` resumes the ticket.
