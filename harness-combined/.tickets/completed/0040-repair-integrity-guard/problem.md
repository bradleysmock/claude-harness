# Problem Statement

**Ticket**: 0040
**Title**: Repair-integrity guard against gate gaming
**Date**: 2026-07-05

## Problem

The build/repair loop instructs the model to "fix the specific file:line locations" but
nothing prevents or detects degenerate repairs that pass gates by weakening the safety
net: deleting or skipping failing tests, loosening assertions, or adding suppression
pragmas. Worse, pre_write_guard.py explicitly treats nosec, nolint, eslint-disable,
ts-expect-error, and noqa as justification markers that bypass the guard — exactly the
tokens a gaming repair would add.

## Impact

- A repair round can turn a red gate green without fixing the defect; the critic is the
  only backstop and is never told to compare tests across rounds.
- Suppression pragmas accumulate silently in delivered code.
- The harness's central quality claim (gate-verified output) is unsound under its own
  autonomous repair pressure.

## Success Criteria

- A deterministic check fails any repair round that deletes/skips tests or adds
  unexplained suppressions, and re-enters repair with corrective instruction.
- Bare suppression markers no longer bypass pre_write_guard; a reason is required.
- Net-new suppressions on the branch are surfaced at turn end.
- The code-mode critic explicitly checks for weakened tests.

## Out of Scope

- Mutation testing and coverage floors (see tickets 0011 and 0025).
- Judging whether a documented suppression reason is adequate — that stays with review.
