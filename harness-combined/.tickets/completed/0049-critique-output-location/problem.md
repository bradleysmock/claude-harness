# Problem Statement

**Ticket**: 0049
**Title**: Move /critique output out of cwd into .harness/critiques/
**Date**: 2026-07-05

## Problem

The critique skill writes its report to CRITIQUE.md in the current working directory
with a fixed name. Successive critiques overwrite each other; the file lands wherever
the session happens to be — including inside a ticket worktree, where the next
git add in the build flow commits it into the delivery squash; and nothing downstream
(status, deliver learnings, future reviews) ever reads it.

## Impact

- Critique history is lost on every re-run.
- Review reports leak into delivered code as accidental repo files.
- The report is a dead end: no other harness surface can find it later.

## Success Criteria

- Critique reports are written to a stable, git-ignored harness location with unique
  names.
- Ticket-scoped critiques leave a pointer in the ticket's findings record.
- /status can surface recent critiques.

## Out of Scope

- Changing the report's content or format.
- The review skill (inline-only, writes no file) and critic subagent output handling
  (ticket 0042).
