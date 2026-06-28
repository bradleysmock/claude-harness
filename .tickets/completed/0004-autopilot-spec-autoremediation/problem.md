# Problem Statement

**Ticket**: 0004
**Title**: Autopilot auto-remediates score-spec BLOCKs instead of bailing
**Date**: 2026-06-27

## Problem

In autopilot mode, the score-spec gate (run via `build-ticket.md` Step 1) is a
hard stop: any BLOCK verdict halts the run before a worktree is created and asks
the lead to fix `solution.md`/`requirements.md` (or run `/refine`) and re-run.
Many BLOCKs are trivial and mechanically fixable — e.g. an FR missing its Test
Plan row, or a `should`/`may` that needs to be `must` — yet autopilot bails and
even names the one-line fix it could have made itself.

## Impact

- Lead is interrupted for clerical edits the harness already diagnosed.
- "Autonomous" pipeline is not autonomous for the most common spec-quality miss.
- Round-trips (fix → re-run autopilot) waste lead time and a fresh session each.

## Success Criteria

- In autopilot mode, a score-spec BLOCK no longer halts immediately.
- Mechanically-fixable checks (missing/phantom Test Plan rows, non-imperative FR
  language) are auto-corrected inline, then the spec is re-scored.
- Checks requiring semantic judgment are routed through an autonomous `/refine`
  pass, then re-scored.
- Bail-out to the lead happens only after remediation is attempted and the
  verdict is still BLOCK (bounded, no infinite loop).
- Interactive `/build` and `/write-spec` keep their existing hard-stop behavior.

## Out of Scope

- Changing the score-spec checks themselves or their severities.
- Auto-remediation for the post-build critic / repair loop (already exists).
- Any change to interactive (non-autopilot) gate behavior.
