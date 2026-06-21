# Problem Statement

**Ticket**: 0020
**Title**: Rollback Skill
**Date**: 2026-06-21

## Problem

When a delivered ticket introduces a regression, the harness operator must manually identify the merge commit and construct a revert. There is no automated path from ticket number to a clean, standardized git revert. This is a gap in the pipeline's delivery lifecycle — delivery is covered, but rollback is not.

## Impact

Harness operators lose time manually searching git log, constructing revert commands, and writing consistent commit messages under incident pressure. Without guardrails, ambiguous or incorrect reverts risk corrupting the working tree or reverting the wrong commit.

## Success Criteria

- `/rollback XXXX` locates the merge commit for ticket XXXX by scanning git log for the ticket number in commit messages.
- Running without `--dry-run` executes `git revert` with a standardized commit message referencing the ticket number and title.
- `--dry-run` flag previews what would be reverted without making any git changes.
- Warns and stops if the ticket is not in "done" status.
- Warns and stops if no merge commit can be unambiguously identified (zero matches or multiple matches).
- Operator is shown the commit SHA and summary before any revert is executed (or as the dry-run output).

## Out of Scope

- Reverting partial changes (file-level or hunk-level) — full commit revert only.
- Reverting tickets that were not merged via a single identifiable commit.
- Automated re-delivery or re-testing after rollback.
- Multi-ticket rollback in a single invocation.
