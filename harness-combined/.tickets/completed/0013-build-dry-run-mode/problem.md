# Problem Statement

**Ticket**: 0013
**Title**: Build --dry-run mode
**Date**: 2026-06-21

## Problem

The `/build` command commits implementation files to the worktree without giving lead engineers an opportunity to review the full gate+critic picture and planned file changes before that write happens. On sensitive codebases, AI-generated implementation plans need to be auditable before any files are written. There is currently no way to invoke all gate phases and the critic agent without also producing implementation output.

## Impact

- Lead engineers on sensitive codebases cannot audit the gate-findings, critic output, and planned file changes before committing to a build.
- If a build produces problematic output, the lead must review after the fact and may need to manually revert worktree changes.
- The lack of a preview step reduces trust in AI-generated builds and forces a reactive rather than proactive review workflow.

## Success Criteria

- `/build --dry-run XXXX` runs all gate phases in full and produces `gate-findings.md`.
- The critic agent runs in full and produces its output.
- A plan of what implementation files would be created/modified is produced, with "would write: <file>" lines for each planned change.
- No implementation files are written to the worktree during a dry run.
- The lead can inspect all dry-run output before deciding to proceed with a real build.

## Out of Scope

- Partial dry runs (e.g. gates only, no critic).
- Persisting dry-run output as a permanent artifact type beyond the current session.
- Auto-approval or auto-continuation from dry-run to live build without lead action.
