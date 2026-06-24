# Harness Progress Checklist — Design

**Date**: 2026-06-23
**Status**: Approved (brainstorm) — pending implementation plan
**Topic**: Make multi-stage harness commands always display a live stage-progress checklist.

## Problem

Multi-stage harness commands (`/autopilot`, `/build`, `/problem`, `/write-spec`, `/deliver`) sometimes show a progress checklist in Claude Code's native todo UI — e.g.:

```
Building 0077… (9m 26s)
✔ Generate specs + s…
◼ Build 0077 in work…
◻ Critic + auto-repa…
◻ Auto-deliver 0077
```

…but usually not. The status section appears only when the model *spontaneously* decides to maintain a todo list, because **no harness command or flow file instructs it to**. `autopilot.md`, `autopilot-ticket.md`, and the build/deliver/problem flows contain zero todo/task instructions. The result is an inconsistent, unpredictable progress display during exactly the long-running autonomous phases where the lead most wants to see where things stand.

## Goals

- Every multi-stage harness command reliably shows a stage-progress checklist from start to finish.
- Stage labels are short, consistent, and meaningful (render cleanly in the truncated todo UI).
- One source of truth for *how* the checklist is maintained; each flow declares only *its* stages (DRY).

## Non-Goals

- Single-step commands (`/gate`, `/cancel`, `/reopen`, `/status`, `/init`, `/refine`) do not get a checklist.
- No deterministic enforcement hook (see Constraint below).
- No change to what the commands actually do — this is display-only.

## Key Constraint (mechanism)

The todo list is **agent-driven**: only the agent can populate it (via the `TodoWrite` tool). A hook cannot inject todos, so — unlike the ticket-commit guard — this **cannot be enforced deterministically**. The available lever is *instructions*. The current flakiness is because there are none. The fix makes checklist creation the explicit, mandated **first action** of each multi-stage flow with exact stage labels, which is as reliable as the mechanism permits. This is a best-effort guarantee by prominence + specificity, not a hard one.

## Approach (chosen)

**Shared convention + per-flow stage lists.** Rejected alternatives: inline-everywhere (repetition, drift, no single source); a single CLAUDE.md global rule (too far from the action, no per-command labels so the model invents inconsistent ones).

## Design

### 1. Shared convention (one place)

Add a **"Progress checklist"** subsection to `context/harness-reference.md` describing the mechanism every multi-stage flow follows:

- As the **first action** of the flow, create a todo list (via the `TodoWrite` tool) with one item per declared stage, all `pending`.
- Mark a stage `in_progress` when starting it and `completed` when it finishes; keep **exactly one** `in_progress` at a time.
- Keep labels short (≤ ~5 words) so they render in the truncated UI.
- If the flow stops early (clarity check fails, status precondition unmet, error), leave the checklist reflecting the true state — do not mark unreached stages completed.

### 2. Per-flow stage declarations

Each multi-stage command/flow gets a short **"Progress checklist"** block at the very top (before its first step) that lists its stage labels and points to the convention in `harness-reference.md`. Stage labels:

| Command / flow file | Stage labels |
|---|---|
| `commands/autopilot.md` → `context/flows/autopilot-ticket.md` | Generate specs (if needed) · Build XXXX in worktree · Critic + auto-repair · Auto-deliver XXXX |
| `context/flows/build-ticket.md` | Generate specs (if needed) · Build XXXX in worktree · Critic review + auto-repair · Present diff (Checkpoint 2) |
| `context/flows/build-spec.md` | Generate spec (if needed) · Run gate engine · Produce artifact |
| `commands/problem.md` | Clarity check · Claim ticket · Problem · Requirements · Tech-stack advisor · Solution · Critic loop · Checkpoint 1 |
| `context/flows/write-spec-ticket.md` & `write-spec-spec.md` | Analyze (spec vs task DAG) · Write spec(s) |
| `context/flows/deliver-ticket.md` | Merge worktree · Status → done + archive · Cleanup (worktree/branch) |

Notes:
- `/problem` includes **all phases** (per lead decision), Phase 0 Clarity check through Checkpoint 1, including the Tech-stack advisor phase.
- The autopilot checklist is owned by `autopilot-ticket.md` (it diverges from `build-ticket.md` at Steps A/B). `autopilot.md` points into that flow, so the checklist block lives in the flow file.
- `build-ticket.md` is read by both `/build` and `/autopilot`. To avoid a double checklist, the stage block in `build-ticket.md` is framed as the `/build` checklist; `autopilot-ticket.md` declares its own (which supersedes it) and instructs the agent not to create a second list when running under autopilot.

### 3. Placement rationale

The block goes at the very top of each flow (the first thing the agent reads and acts on) so the todo list exists before any stage work begins — maximizing the chance it is created every run.

## Risks & Mitigations

- **Model still skips it occasionally** → mitigated by prominent placement as the mandated first action and explicit labels; cannot be fully eliminated (agent-driven mechanism). Accepted.
- **Double checklist under autopilot** (build-ticket + autopilot both declaring) → autopilot-ticket.md owns the list and tells the agent not to create a second; build-ticket's block is conditional on not already running under a parent flow.
- **Label drift / inconsistency** → the shared convention + this spec's table are the single reference for labels.
- **Stale UI on early exit** → convention explicitly says to leave the checklist reflecting true state on early stop.

## Success Criteria

- Each of the six flow/command files above contains a "Progress checklist" block declaring its stages and referencing the convention.
- `harness-reference.md` contains the "Progress checklist" convention subsection.
- Running `/autopilot`, `/build`, `/problem`, `/write-spec`, `/deliver` produces a stage checklist in the todo UI matching the declared labels.
- No checklist block is added to single-step commands.
- Verifiable by content-assertion tests (the repo's convention) that each named file contains its checklist block and the expected stage labels, and the convention section exists.
