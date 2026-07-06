# Problem Statement

**Ticket**: 0039
**Title**: Worktree-first ticket resolution and branch-only commit fixes
**Date**: 2026-07-05

## Problem

The branch-at-claim redesign made all post-claim ticket state branch-only: main carries
only the claim stub and the delivery squash (harness-reference.md, Status transitions).
But four flows still instruct commits of post-claim state to main, and every downstream
resolver reads the root .tickets copy of status.md — which, per the invariant, says
"claimed" until delivery. Taken literally, /autopilot refuses every correctly-claimed
ticket and /deliver can never confirm review-ready.

## Impact

- autopilot-ticket.md Step A, skills/review Step 7, commands/refine.md, and
  spec-remediation.md commit to main, violating the two-commits-on-main invariant.
- commands/autopilot.md, build-ticket.md Step 1, write-spec-ticket.md Step 1,
  commands/gate.md, and deliver-ticket.md Step 1 resolve status from the stale main copy.
- spec-remediation.md and build-ticket.md Step 1.2 retain pre-redesign text claiming no
  worktree exists before build.
- The pipeline currently works only because the model improvises around the contradiction.

## Success Criteria

- A single authoritative resolution rule exists in harness-reference.md and is cited by
  every resolver flow.
- No flow instructs a post-claim, pre-delivery commit to main.
- Pre-redesign "no worktree yet" remnants are removed.
- A docs-consistency test guards the conventions.

## Out of Scope

- Changing the claim protocol, squash delivery mechanics, or ticket.py helpers.
- Migrating existing in-flight tickets.
