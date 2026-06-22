# Problem Statement

**Ticket**: 0013
**Title**: Inline PR Comment Posting
**Date**: 2026-06-21

## Problem

Gate and critic findings are currently written to terminal output and `gate-findings.md`, requiring the harness operator to manually cross-reference findings with the PR diff in a browser. This context-switching slows review triage and means findings are not visible to PR reviewers who weren't present at the terminal session.

## Impact

- Harness operators must manually locate file:line positions in GitHub UI after reading terminal output.
- PR reviewers lack visibility into gate and critic findings unless the operator manually copies them.
- Finding resolution is not tracked inline with the code changes that caused them.

## Success Criteria

- After a gate run, each finding in `gate-findings.md` with a file:line reference is posted as an inline PR review comment via `gh pr review`.
- After a critic review, BLOCKER and MAJOR findings become inline review comments; MINOR and OBS become review suggestions.
- When no open PR exists for the current branch, output falls back to terminal only.
- When `gh` is not installed or not authenticated, output falls back gracefully with a clear warning.
- No duplicate comments are posted on re-runs (idempotency via comment deduplication).

## Out of Scope

- Support for non-GitHub VCS hosts (GitLab, Bitbucket).
- Automatically resolving or dismissing outdated comments.
- Posting comments on PRs the operator does not own.
- CI/CD integration (this targets local harness runs, not server-side pipelines).
