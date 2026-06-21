# Problem Statement

**Ticket**: 0015
**Title**: Bisect Helper
**Date**: 2026-06-21

## Problem

When a regression is discovered, harness operators must manually correlate git bisect with ticket metadata to identify which ticket introduced the bug. This requires cross-referencing merge commits, ticket branches, and test output manually — a slow, error-prone process that breaks the ticket-centric mental model of the harness.

## Impact

- Harness operators lose time manually running `git bisect` and cross-referencing merge commits with ticket directories.
- Without ticket-aware bisect, the regression source is described in raw git terms (commit SHA) rather than the harness's ticket vocabulary, slowing root-cause communication.
- Regressions caught late (after multiple tickets merge) compound the manual effort.

## Success Criteria

- `/bisect` command accepts a known-good ticket (or HEAD~N) and failing state (current HEAD or another ticket).
- The command resolves the known-good and known-bad git boundaries from ticket merge commits automatically.
- The command runs the project's configured test command at each bisect step without operator intervention.
- The command reports the culprit commit SHA and, when the commit falls within a ticket's branch range, names the ticket: "regression introduced in commit <sha>, part of ticket XXXX".
- The bisect session leaves the repo in a clean state (bisect reset) regardless of outcome.

## Out of Scope

- Visual diff or patch review of the culprit commit.
- Automatic filing of a new ticket for the regression.
- Support for non-git VCS.
- Bisecting across forks or remote refs beyond what `git bisect` natively supports.
