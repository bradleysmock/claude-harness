# Problem Statement

**Ticket**: 0008
**Title**: Ticket velocity report
**Date**: 2026-06-21

## Problem

Harness operators have no visibility into how long tickets take from problem creation to done. Without cycle-time data, slowdowns are invisible until they become crises. The harness already records timestamps in `status.md` files and `git log`, but nothing aggregates them into a readable trend.

## Impact

- Lead engineers cannot track team throughput or spot velocity regressions.
- No data to inform estimates or identify which ticket types take longest.
- Sprint retrospectives lack objective delivery-pace evidence.

## Success Criteria

- `/velocity` command reads completed ticket `status.md` files and computes cycle time (days from `problem` status timestamp to `done`).
- Output is a formatted table grouped by week (or sprint), showing per-ticket duration, weekly average, and a simple trend indicator.
- Works from the harness root without additional setup.
- Handles edge cases: no completed tickets, missing timestamps, incomplete status history.

## Out of Scope

- Real-time or live dashboard; this is a CLI report only.
- Integration with external project-management tools (Jira, Linear, etc.).
- Predictive forecasting or burn-down charts.
- Tickets currently in flight (non-completed).
