# Problem Statement

**Ticket**: 0009
**Title**: Spec diff on refine
**Date**: 2026-06-21

## Problem

When `/refine` or `/replan` updates `solution.md` or `requirements.md`, the file is silently overwritten with no visibility into what changed. The harness operator has no way to review what the LLM actually modified before the change is committed, making it easy to miss regressions, scope creep, or unintended rewrites in ticket artifacts.

## Impact

- Harness operators cannot audit what a refine/replan changed without manually diffing git history.
- Silent overwrites erode trust in the refine pipeline — operators are uncertain whether the update improved, regressed, or drifted the design.
- Any command that modifies existing ticket artifacts after initial creation shares this gap.

## Success Criteria

- Before any artifact file is overwritten by `/refine`, `/replan`, or equivalent commands, a unified diff of the pending change is printed to the terminal.
- The diff is shown inline in the conversation output before the write is committed.
- An optional `--diff` flag can gate the behavior (show diff only when flag is passed), or diff is on by default — either is acceptable; the design decision is deferred to requirements.
- The feature applies consistently to all commands that modify existing ticket artifacts post-creation.
- If the file does not yet exist (first write), no diff is shown.

## Out of Scope

- Diffing files outside the `.tickets/` directory.
- Storing or persisting diffs as separate artifact files.
- Interactive approval/rejection of the diff within the same command (that is the `/refine` approval flow, not this ticket).
