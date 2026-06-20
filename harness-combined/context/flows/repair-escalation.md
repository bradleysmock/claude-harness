# Flow: repair-escalation

Entered when BLOCKER/MAJOR findings remain after `MAX_REPAIR_ATTEMPTS` in the post-build critic loop. The worktree exists at `.worktrees/XXXX-slug/`, `gate-findings.md` is current at `.tickets/XXXX-slug/gate-findings.md`, and the latest critic report is in context.

This flow returns one of two signals to the caller:
- **succeeded**: all BLOCKER/MAJOR findings cleared
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

Apply the subagent's fix strategy: make the targeted edits directly in `.worktrees/XXXX-slug/`, then run:

```
gate_run_on_dir(".worktrees/XXXX-slug", "auto", project_root)
```

Re-spawn the critic subagent (same Phase and Ticket as the caller, next Round number). Display its report verbatim. Allow up to `MAX_REPAIR_ATTEMPTS` additional repair rounds.

- If the critic returns no BLOCKER/MAJOR findings → **return succeeded** to caller.
- If BLOCKER/MAJOR findings remain after `MAX_REPAIR_ATTEMPTS` → proceed to Phase 2.

## Phase 2 — Strategy reset

Delete the failing target file(s) from the worktree (do not use `git checkout` — the goal is a clean slate, not the last committed version):

```
rm .worktrees/XXXX-slug/<target_file>
```

Rewrite the target file(s) from the spec. Prepend the following to the generation context before writing:

> Previous approaches tried: [brief summary of what the original repair loop and Phase 1 attempted]. These failed because: [root cause identified by the Phase 1 diagnostic subagent]. Do not use these approaches.

Run `gate_run_on_dir` and re-spawn the critic. Display the critic's report verbatim. Allow up to `MAX_REPAIR_ATTEMPTS` rounds.

- If the critic returns no BLOCKER/MAJOR findings → **return succeeded** to caller.
- If BLOCKER/MAJOR findings remain → **return exhausted** to caller.
