# Problem Statement

**Ticket**: 0028
**Title**: GitHub PR auto-creation
**Date**: 2026-06-21

## Problem

The `/deliver` command merges a ticket branch to main locally but provides no path to open a GitHub PR from the same workflow. Harness operators who want code review, audit trails, or CI checks on GitHub must manually push the branch and create a PR with appropriate content — a context-switching interruption that is error-prone and tedious.

## Impact

- Harness operators lose time manually writing PR titles, summaries, and test checklists that are already captured in `solution.md` and `requirements.md`.
- Without a linked PR, GitHub lacks the audit trail connecting delivered code to its ticket design artifacts.
- Teams relying on GitHub branch protections or CI cannot use `/deliver` in their workflow without manual follow-up steps.

## Success Criteria

- A `--pr` flag on `/deliver` pushes the ticket branch to the remote and opens a GitHub PR.
- PR title is populated from the ticket title.
- PR body is derived from `solution.md` and includes the test plan from `requirements.md` as a checklist.
- PR body links back to the ticket number.
- If `gh` is not installed or not authenticated, PR creation is skipped with a clear warning; the merge still completes.
- The `--pr` flag works alongside the standard merge-to-main delivery path (not a replacement).

## Out of Scope

- Support for non-GitHub remotes (GitLab, Bitbucket).
- Automatically assigning reviewers, labels, or milestones on the PR.
- Merging the PR via GitHub (the local merge-to-main path remains the delivery mechanism).
- Modifying the existing `/deliver` behavior when `--pr` is not passed.
