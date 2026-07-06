Manual gate runner — runs the full gate suite against a ticket's worktree using the harness MCP tools. Writes structured findings to `.tickets/XXXX-<slug>/gate-findings.md`.

## Ticket resolution

A ticket number argument is required. If none is provided, scan `.tickets/` (not `.tickets/completed/`) for tickets with `status: implementing` or `status: review-ready`. If exactly one exists, use it. Otherwise list candidates and stop. For direct ticket ID resolution, check `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/`.

Read each ticket's status via the **Ticket resolution** rule in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`: when a worktree `.worktrees/XXXX-<slug>` exists, its `.tickets/` copy of `status.md` is authoritative (it carries `implementing` / `review-ready`); the root copy shows only claim/terminal states.

## Steps

1. **Determine worktree path** from `status.md`: read the `branch` field (e.g. `ticket/XXXX-<slug>`), strip the `ticket/` prefix, resolve `.worktrees/XXXX-<slug>` relative to project root. Confirm the directory exists.

2. **Run structured gates** via the MCP tool:
   ```
   gate_run_on_dir(".worktrees/XXXX-<slug>", "auto", project_root, fail_fast=False)
   ```
   This runs all gates (no fail-fast) for **every** detected language stack and returns the complete picture including passed gates. On a polyglot repo (e.g. Python backend + TypeScript frontend) the response carries a `languages` list and a pre-rendered `findings_md` body.

3. **Write `.tickets/XXXX-<slug>/gate-findings.md`**. When the response includes `findings_md`, write it verbatim under the header. Otherwise render the same structure yourself:

   ```markdown
   # Gate Findings — XXXX-<slug>

   **Run at**: YYYY-MM-DD HH:MM
   **Worktree**: .worktrees/XXXX-<slug>
   **Languages detected**: <language(s), comma-separated>

   ## <language> / <gate-name>

   **Status**: PASS | FAIL
   **Duration**: NNNms

   <For each failing error:>
   - `<file>:<line>` [`<code>`]: <message>

   <"clean" if no errors>
   ```

   One section per gate, per language, in the order they ran. Section headings are `## <language> / <gate-name>` when more than one language is detected; with a single language the heading is the bare `## <gate-name>` and the header reads `**Language detected**: <language>` (singular) — this preserves the pre-polyglot single-language report shape.

4. **Print summary line**: one `<language>=<PASS|FAIL: gate-names-failing>` token per detected language, e.g. `gate: python=PASS typescript=FAIL: lint`. With a single language this collapses to the original `gate: <language>=<PASS|FAIL: gate-names-failing>`. A gate that fails in **any** language makes the overall run non-zero.

   If the response is a `CONFIG_ERROR` (a malformed `[gates]` override block in `_standards.md`), report it as a failing run and surface the `CONFIG_ERROR` finding — the gate fails closed and does **not** fall back to the default commands.

## Notes

- This command **does not fix findings** — it records them. The caller decides what to do.
- The structured `file:line` error locations in `gate-findings.md` are what the critic reads to avoid re-flagging gate issues.
- `/build` calls this automatically; run it manually when you need a fresh gate report without re-running the full build cycle.
