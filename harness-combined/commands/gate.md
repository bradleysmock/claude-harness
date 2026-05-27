Manual gate runner — runs the full gate suite against a ticket's worktree using the harness MCP tools. Writes structured findings to `.tickets/XXXX-<slug>/gate-findings.md`.

## Ticket resolution

A ticket number argument is required. If none is provided, scan `.tickets/` for tickets with `status: implementing` or `status: review-ready`. If exactly one exists, use it. Otherwise list candidates and stop.

## Steps

1. **Determine worktree path** from `status.md`: read the `branch` field (e.g. `ticket/XXXX-<slug>`), strip the `ticket/` prefix, resolve `.worktrees/XXXX-<slug>` relative to project root. Confirm the directory exists.

2. **Run structured gates** via the MCP tool:
   ```
   gate_run_on_dir_full(".worktrees/XXXX-<slug>", "auto", project_root)
   ```
   This runs all gates (no fail-fast) and returns the complete picture including passed gates.

3. **Write `.tickets/XXXX-<slug>/gate-findings.md`**:

   ```markdown
   # Gate Findings — XXXX-<slug>

   **Run at**: YYYY-MM-DD HH:MM
   **Worktree**: .worktrees/XXXX-<slug>
   **Language detected**: <language>

   ## <gate-name>

   **Status**: PASS | FAIL
   **Duration**: NNNms

   <For each failing error:>
   - `<file>:<line>` [`<code>`]: <message>

   <"clean" if no errors>
   ```

   One section per gate in the order they ran.

4. **Print summary line**: `gate: <language>=<PASS|FAIL: gate-names-failing>`

## Notes

- This command **does not fix findings** — it records them. The caller decides what to do.
- The structured `file:line` error locations in `gate-findings.md` are what the critic reads to avoid re-flagging gate issues.
- `/build` calls this automatically; run it manually when you need a fresh gate report without re-running the full build cycle.
