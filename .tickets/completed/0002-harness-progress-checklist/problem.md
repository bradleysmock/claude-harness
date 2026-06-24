# Problem Statement

**Ticket**: 0002
**Title**: Always show a stage-progress checklist for multi-stage harness commands
**Date**: 2026-06-23

## Problem

Multi-stage harness commands (`/autopilot`, `/build`, `/problem`, `/write-spec`, `/deliver`) only *sometimes* render Claude Code's native todo-list progress UI (the `✔ / ◼ / ◻` checklist with an elapsed timer). It appears only when the model spontaneously decides to maintain a todo list, because no command or flow file instructs it to — `autopilot.md`, `autopilot-ticket.md`, and the build/deliver/problem flows contain zero todo instructions.

## Impact

- Affects the lead running long autonomous phases (autopilot/build), where progress visibility matters most.
- Without it, the lead cannot see which stage is active or how far along a multi-minute run is — the run looks opaque or stalled.
- Inconsistent UX: the same command shows progress on one run and nothing on the next.

## Success Criteria

- Each multi-stage command/flow reliably creates and updates a stage checklist via the `TodoWrite` tool, from start to finish.
- Stage labels are short, consistent, and meaningful (render cleanly when truncated).
- A single shared convention defines *how* the checklist is maintained; each flow declares only *its* stages (no duplicated mechanism prose).
- Single-step commands (`/gate`, `/cancel`, `/reopen`, `/status`, `/init`, `/refine`) get no checklist.

## Out of Scope

- Deterministic enforcement: the todo list is agent-driven (only the agent can call `TodoWrite`); a hook cannot inject todos. This is a best-effort guarantee by prominent instruction, not a hard one.
- `/deliver` spec-mode (`deliver-spec.md`) — a single artifact write to its target file; treated as effectively single-step, so no checklist. (Ticket-mode `/deliver` is covered.)
- Any change to what the commands actually do — this is display-only.
