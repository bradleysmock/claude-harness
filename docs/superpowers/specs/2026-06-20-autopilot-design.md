# Design: `/autopilot` — Autonomous Build-to-Deliver Pipeline

**Date**: 2026-06-20  
**Status**: Approved

---

## Summary

Add a `/autopilot XXXX` command to harness-combined that chains build → extended repair → deliver without human re-invocation. The intended workflow becomes two command invocations: `/problem` (design pipeline, stops at Checkpoint 1 for approval) and `/autopilot` (execution pipeline, runs to completion).

Existing commands are unchanged. `/build` remains interactive and bounded.

---

## Motivation

The current post-`/problem` workflow requires multiple manual re-invocations:
- `/write-spec XXXX` (optional but recommended)
- `/build XXXX`
- Review diff → `/deliver XXXX`
- If repair exhausts → advise → `/build XXXX` again

These are sequencing steps, not design decisions. `/autopilot` eliminates them.

---

## New Files (3)

```
commands/autopilot.md                    ← entry point, mode dispatch
context/flows/autopilot-ticket.md        ← orchestration flow
context/flows/repair-escalation.md       ← escalated repair: diagnostic → strategy reset
```

No existing files are modified.

---

## `commands/autopilot.md`

Thin dispatch layer. Resolves the ticket (same scan order as `/build`), confirms `status: solution`, announces the resolved ticket, then reads and follows `autopilot-ticket.md`. If `$ARGUMENTS` is empty, scans `.tickets/` for exactly one ticket at `status: solution`; if multiple exist, lists them and requires the lead to specify one. If the ticket is not at `status: solution`, tells the lead to run `/problem XXXX` first.

---

## `context/flows/autopilot-ticket.md`

Orchestration layer. Delegates shared build work to `build-ticket.md` rather than duplicating it.

**Preamble**: Announce "autopilot mode for XXXX-slug".

**Steps 1–7c**: Read `build-ticket.md` and follow it exactly — worktree creation, spec execution, gate repair loop, commit, diff, critic spawn, BLOCKER/MAJOR auto-repair. When BLOCKER/MAJOR findings still remain after `MAX_REPAIR_ATTEMPTS` repair rounds (the condition that would trigger `build-ticket.md` Step 7d), stop and return to this flow instead.

**Divergence A — repair exhaustion (intercepting 7d)**:  
Do not transition to `changes-requested`. Do not ask the lead.  
Read `repair-escalation.md` and follow it.  
- If repair-escalation returns **succeeded** → go to Auto-deliver.  
- If repair-escalation returns **exhausted** → fall back to the same `changes-requested` transition and lead escalation that `build-ticket.md` Step 7d would have done, noting that diagnostic and strategy-reset escalation were already attempted.

**Divergence B — clean build (intercepting 7b/7c)**:  
Do not present options and stop. Go directly to Auto-deliver.

**Auto-deliver**:  
Show the diff (`git -C .worktrees/XXXX-slug diff main`) — informational, not a gate.  
Read `deliver-ticket.md` and follow it in full (merge, archive, cleanup).  
No approval prompt required.

---

## `context/flows/repair-escalation.md`

Entered when BLOCKER/MAJOR findings remain after `MAX_REPAIR_ATTEMPTS`. The worktree, gate findings, and latest critic report are in place.

### Phase 1 — Diagnostic subagent

Spawn a `claude` subagent (fresh context, read-only) with this brief:

> You are a diagnostic engineer. A build repair loop has exhausted `MAX_REPAIR_ATTEMPTS` without clearing all BLOCKER/MAJOR findings. Do not write or edit anything — only diagnose.
>
> Read:
> - The failing spec file(s)
> - The current worktree implementation and tests
> - The latest critic findings (BLOCKER/MAJOR only)
> - `.tickets/XXXX-slug/gate-findings.md`
>
> Produce exactly three things:
> 1. **Root cause** — what is fundamentally wrong (not a restatement of error messages)
> 2. **Fix strategy** — a concrete approach that avoids what was already tried
> 3. **Target locations** — which files and sections to change

Apply the subagent's strategy: make targeted edits in the worktree, re-run `gate_run_on_dir`, re-spawn the critic. Allow up to `MAX_REPAIR_ATTEMPTS` additional rounds.

- If BLOCKER/MAJOR findings clear → return **succeeded** to caller.
- If findings still remain → Phase 2.

### Phase 2 — Strategy reset

Discard the failing target file(s) from the worktree. Rewrite them from the spec, prepending to the generation context:

> Previous approaches tried: [summary of what was attempted in the normal loop and Phase 1]. These failed because: [root cause from Phase 1 diagnostic]. Do not use these approaches.

Run `gate_run_on_dir` and re-spawn the critic. Allow up to `MAX_REPAIR_ATTEMPTS` rounds on the reset implementation.

- If BLOCKER/MAJOR findings clear → return **succeeded** to caller.
- If findings still remain → return **exhausted** to caller.

### Ordering rationale

Diagnostic runs first (preserves context, targeted, cheap). Strategy reset only fires if the diagnosis didn't hold — it's the heavier, context-discarding option.

---

## Workflow summary

```
/problem "description"
  → problem + requirements + solution + design critic loop (autonomous)
  → Checkpoint 1: approve?          ← only human decision in the pipeline

/clear
/autopilot XXXX
  → spec generation (if needed)
  → build + gate repair (MAX_REPAIR_ATTEMPTS)
  → post-build critic + BLOCKER/MAJOR auto-repair
     → if exhausted: diagnostic subagent → apply strategy → re-verify
     → if still exhausted: strategy reset (discard + rewrite) → re-verify
     → if still exhausted: escalate to lead
  → show diff
  → deliver (merge + archive)       ← no prompt
```

---

## What is not changed

- `build-ticket.md` — untouched; `/build` keeps its bounded, interactive behavior
- All other commands and flows — untouched
- The Stop hook, PostWrite hook — untouched
- `deliver-ticket.md` — reused as-is; autopilot calls it directly

---

## Out of scope

- Spec-mode autopilot (standalone `.harness/specs/` runs without a ticket)
- Parallel multi-ticket autopilot dispatch
- Background / scheduled autopilot runs
