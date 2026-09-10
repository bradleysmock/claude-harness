# Problem Statement

**Ticket**: 0082
**Title**: Notify the lead when autopilot-watch dispatches need attention
**Date**: 2026-09-10

## Problem

`autopilot_watch.py` (ticket 0078) dispatches `/harness-combined:autopilot
XXXX` and blocks until it exits, but nothing surfaces the outcome to the
lead. Verified live this session: a dispatch that ends in
`changes-requested`, an errored launch, or a ticket stuck mid-build is
indistinguishable from a healthy in-progress run unless the lead manually
reads `status.md`, the per-ticket log, and `bin/autopilot-watch status` —
none of which are pushed to them.

## Impact

- A watcher left running unattended can sit on a ticket that needs the
  lead's input (repair exhaustion, a score-spec bail) for however long
  until someone happens to check — defeating the point of "unattended."
- There's no way to distinguish "still building" from "finished and
  waiting for you" without manual polling across three different places.

## Success Criteria

- After each dispatch, the watcher classifies the outcome from the
  ticket's on-disk `status.md` (not fragile log-text parsing): success
  (`done`) vs. needs-attention (`changes-requested`, an unchanged/stuck
  status, or the dispatch itself erroring to launch).
- Needs-attention outcomes are recorded to a durable, greppable log with
  ticket, reason, and timestamp.
- A best-effort OS desktop notification fires on a needs-attention
  outcome — skip-safe: never crashes or blocks a tick if unsupported.
- `bin/autopilot-watch status` surfaces needs-attention entries, not just
  the last tick's summary.
- Document a "watch via Claude" pattern using the existing `/loop` skill
  to periodically report needs-attention entries conversationally in an
  interactive session — no new code, just documented usage.

## Out of Scope

- A live question/answer channel with the dispatched headless session —
  autopilot never asks the lead mid-build by design; notification here is
  post-hoc status only.
- Slack/email/SMS or other external integrations.
- Any change to `autopilot-ticket.md`'s own prose messages.
