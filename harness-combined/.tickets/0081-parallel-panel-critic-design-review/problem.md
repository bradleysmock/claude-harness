# Problem Statement

**Ticket**: 0081
**Title**: Parallelize multi-panel design-review critic rounds
**Date**: 2026-09-10

## Problem

`/problem` Phase 5 spawns one critic subagent per round; when multiple
expert panels activate (e.g. Core + Python + Testing + Shell, as happened
for ticket 0078 in this session), that single agent reads every panel file
and applies every panel's dimensions sequentially in one long call —
observed at 3–7 minutes and 15–40 tool calls per round this session. The
finding format (`**SEVERITY** · <Panel> / <Dimension> · \`<file>:<line>\``)
is already fully structured and machine-parseable
(`gates/critic_finding_parser.py`), so nothing about the review's *output*
requires one agent to produce it in one pass.

## Impact

- Design-review Checkpoint 1 is gated on the critic loop finishing (up to 2
  rounds); a multi-panel round's wall-clock time is spent sequentially
  reading and applying panels that have no dependency on each other.
- The lead waits longer for Checkpoint 1 on exactly the tickets most likely
  to need a thorough review (many active panels = broad, cross-cutting
  change).

## Success Criteria

- When 2 or more non-Core panels are active for a design review, the
  review runs as one agent per panel (Core plus its problem.md-added
  design-specific evaluations in one agent; each other panel alone in its
  own), in parallel, merged into one findings document with no duplicate
  or dropped findings.
- When 0 or 1 non-Core panel is active, behavior is byte-for-byte identical
  to today: one agent, no split, no merge step (no regression, no added
  overhead for the common case).
- The 2-round-per-Checkpoint-1 budget is unchanged; a "round" still means
  one full pass (now possibly parallel-fanned) with revision in between.

## Out of Scope

- The post-implementation code-review critic (`build-ticket.md` Step 7,
  its incremental-repair-round branching) — design-review only, for now.
- Automatic Secondary-panel escalation logic — stays a manual option the
  orchestrator can exercise after seeing merged reports, not automated.
- Any change to panel *content*, severity vocabulary, or `panel_detect.py`
  itself.
