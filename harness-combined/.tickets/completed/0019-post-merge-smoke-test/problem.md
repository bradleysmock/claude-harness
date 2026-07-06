# Problem Statement

**Ticket**: 0019
**Title**: Post-merge smoke test
**Date**: 2026-06-21

## Problem

After `/deliver` merges a branch into main, there is no automated check that main is still
functional. A regression in the merged code can silently corrupt main, and the next developer
who pulls the branch gets a broken baseline. The only recovery today is manual: the lead
detects the failure, identifies the commit, and runs `git revert` by hand.

## Impact

- Harness operators (lead engineers) may unknowingly merge a breaking change into main.
- Subsequent ticket branches rebased from the broken main will inherit the regression.
- Manual triage and revert is slow and error-prone; the window of a broken main can span hours.

## Success Criteria

- `/deliver` optionally runs a configurable smoke-test command against main after merge.
- If the smoke test exits non-zero, `/deliver` automatically runs `git revert` on the merge
  commit (or warns, depending on mode) and reports the failure clearly.
- The smoke-test command is configured in `.tickets/_standards.md` as `smoke_test_command`.
- A configurable timeout (default 60 s, max 300 s) aborts the command and triggers the same
  failure path if exceeded.
- Two modes: `auto-revert` (default) and `warn-only`; both are configurable in `_standards.md`.
- Smoke-test phase is skipped entirely when no `smoke_test_command` is defined.
- Main is left in the pre-merge state on auto-revert; the merged branch and worktree are NOT
  cleaned up so the lead can rework them.

## Out of Scope

- Running the full test suite as the smoke test (harness does not enforce suite selection).
- Changing the gate engine or the `.build` repair loop.
- Automatic retry of the smoke test.
- Notification integrations (Slack, email, etc.).
