# Problem Statement

**Ticket**: 0004
**Title**: Stale ticket detector
**Date**: 2026-06-21

## Problem

Tickets in the harness can sit idle for days or weeks without the lead noticing. The `updated:` field in each ticket's `status.md` records the last activity date, but nothing surfaces tickets that have gone quiet. Leads have no built-in signal to distinguish actively progressing work from abandoned or blocked tickets until a delivery surprise occurs.

## Impact

Harness operators (lead engineers) may miss blocked or abandoned tickets until sprint review or a deadline miss. Without an idle-detection signal, the cognitive burden of tracking ticket freshness falls entirely on manual inspection of individual status files.

## Success Criteria

- A `/stale` command lists all tickets whose `updated:` date exceeds a configurable idle threshold (default: 7 days).
- Each stale entry shows: ticket number, title, current status, and days idle.
- Threshold is configurable via `_standards.md` key or a `--days` flag on the command.
- `/status` output optionally surfaces a stale-ticket summary (count or list) when stale tickets exist.
- Command works correctly against any mix of ticket statuses (problem, requirements, solution, in-progress, etc.).

## Out of Scope

- Auto-closing or auto-archiving stale tickets.
- Notifications or external alerts (email, Slack, etc.).
- Modifying `updated:` timestamps automatically on any harness action (separate concern).
