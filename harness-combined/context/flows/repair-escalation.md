# Flow: repair-escalation

Entered when BLOCKER/MAJOR findings remain after `MAX_REPAIR_ATTEMPTS` in the post-build critic loop. The worktree exists at `.worktrees/XXXX-slug/`, `gate-findings.md` is current at `.tickets/XXXX-slug/gate-findings.md`, and the latest critic report is in context.

This flow returns one of two signals to the caller:
- **succeeded**: all BLOCKER/MAJOR findings cleared (ticket status remains `review-ready` — unchanged by this flow)
- **exhausted**: findings remain after all phases

## Phase 1 — Diagnostic subagent

Spawn a `claude` subagent (fresh context, read-only — it must not write or edit files) with the following brief. Substitute the actual ticket slug, spec paths, implementation paths, and critic findings before spawning:

> You are a diagnostic engineer. A build repair loop has exhausted MAX_REPAIR_ATTEMPTS without clearing all BLOCKER/MAJOR findings. Do not write or edit anything — only diagnose.
>
> Read:
> - The failing spec file(s): [list paths from `.harness/specs/` or `.harness/tasks/`]
> - The current implementation: [`.worktrees/XXXX-slug/<target_file>`]
> - The current tests: [`.worktrees/XXXX-slug/tests/`]
> - Gate findings: `.tickets/XXXX-slug/gate-findings.md`
> - BLOCKER/MAJOR findings from the latest critic report: [paste them verbatim]
>
> Produce exactly three things:
> 1. **Root cause** — what is fundamentally wrong (not a restatement of error messages)
> 2. **Fix strategy** — a concrete approach that avoids what was already tried
> 3. **Target locations** — which files and sections to change

**Persist the diagnosis before applying any edits.** The diagnostic subagent's output is the highest-value failure artifact in the pipeline — capture it durably first:

1. Append it to the ticket's `critic-findings.md` (the durable sibling of `gate-findings.md` — see "Critic findings file" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`) as its own append-only section headed by the date, preserving the three parts verbatim — **Root cause**, **Fix strategy**, and **Target locations**:

   ```
   ## Escalation diagnosis — <today's date>

   **Root cause**: …
   **Fix strategy**: …
   **Target locations**: …
   ```

   Commit it on the branch (branch-local — it must **not** touch `main`):

   ```
   git -C .worktrees/XXXX-slug add .tickets/XXXX-slug/critic-findings.md
   git -C .worktrees/XXXX-slug commit -m "chore(ticket): XXXX escalation diagnosis"
   ```

2. Record it to the BM25 failure memory under gate `"critic"` so a future repair is warned away from the failed strategy — pass the root cause + failed strategy as the error text:

   ```
   memory(action="record", spec_id="XXXX-slug", gate="critic", errors_text="<root cause + prior failed strategy>", attempt=<repair attempt count>, outcome="escalated", project_root=project_root)
   ```

Apply the subagent's fix strategy: make the targeted edits directly in `.worktrees/XXXX-slug/`, targeting only the file(s) identified in the subagent's "Target locations" output above. Then commit the repair edits:

```
git -C .worktrees/XXXX-slug commit -am "fix: address post-build critic repair-escalation Phase 1 findings"
```

Then run:

```
gate_run_on_dir(".worktrees/XXXX-slug", "auto", project_root)
```

(`project_root` is inherited from the build phase context, loaded in `build-ticket.md` Step 1 from `.harness/config.py`.)

Re-spawn the critic subagent (same Phase and Ticket as the caller, next Round number). Display its report verbatim. **Persist this round**: append the report to `critic-findings.md` as a new `## Round N — <today's date>` section and commit it on the branch (`git -C .worktrees/XXXX-slug commit -am "chore(ticket): XXXX critic findings round N"`) — the same append+commit the caller's `build-ticket.md` Step 7a performs, so *every* critic round (escalation rounds included) lands in the durable file. Allow up to `MAX_REPAIR_ATTEMPTS` additional repair rounds.

- If the critic returns no BLOCKER/MAJOR findings → **return succeeded** to caller.
- If BLOCKER/MAJOR findings remain after `MAX_REPAIR_ATTEMPTS` → proceed to Phase 2.

## Phase 2 — Strategy reset

Delete only the file(s) identified in Phase 1's "Target locations" output from the worktree (do not delete all worktree changes; do not use `git checkout` — the goal is a clean slate for the target files, not the last committed version):

```
rm .worktrees/XXXX-slug/<target_file>
```

Rewrite the target file(s) from the spec. Prepend the following to the generation context before writing:

> Previous approaches tried: [brief summary of what the original repair loop and Phase 1 attempted]. These failed because: [root cause identified by the Phase 1 diagnostic subagent]. Do not use these approaches.

After the rewrite, commit the new implementation:

```
git -C .worktrees/XXXX-slug commit -am "fix: address post-build critic repair-escalation Phase 2 rewrite"
```

Run `gate_run_on_dir` and re-spawn the critic. Display the critic's report verbatim. **Persist this round**: append the report to `critic-findings.md` as a new `## Round N — <today's date>` section and commit it on the branch (`git -C .worktrees/XXXX-slug commit -am "chore(ticket): XXXX critic findings round N"`), exactly as Phase 1 does — no critic round is dropped from the durable file. Allow up to `MAX_REPAIR_ATTEMPTS` rounds.

- If the critic returns no BLOCKER/MAJOR findings → **return succeeded** to caller.
- If BLOCKER/MAJOR findings remain → **return exhausted** to caller.
