# Problem Statement

**Ticket**: 0078
**Title**: Standalone autopilot watcher on lead approval
**Date**: 2026-09-10

## Problem

Checkpoint 1 approval in `/problem` is purely conversational — nothing
persists the lead's "yes" to disk. `status.md` already reads `solution` as of
Phase 4, before the critic loop and before Checkpoint 1 even runs. The lead
wants an opt-in, standalone background watcher that fires `/autopilot XXXX`
automatically once a ticket is approved, without keeping the `/problem`
session open. Today the only path to autopilot is running it manually,
in-session, after approval.

## Impact

- No on-disk signal distinguishes "design drafted, critic still reviewing"
  from "lead said yes, ready to build." A poller watching `status: solution`
  alone cannot tell the two apart and would race ahead of real approval.
- The lead can't step away between approving a design and it starting to
  build — manual `/autopilot` is the only path, and it requires staying at
  the keyboard through the session boundary.
- Two tickets reaching `solution` close together give no ordering signal for
  which was actually approved, so a naive poller could build the wrong one
  first or build an unapproved draft.

## Success Criteria

- Checkpoint 1 approval persists a durable, branch-committed signal distinct
  from `solution`, written only when the lead approves.
- A watcher process, started and stopped independently of any `/problem` or
  `/build` session, polls for approved tickets and invokes `/autopilot XXXX`
  on each, one at a time.
- Manual `/autopilot XXXX` still works unchanged when the watcher isn't
  running — no regression to today's flow.
- The watcher never double-fires on a ticket it has already handed to
  autopilot, whether in progress or already delivered.
- Starting/stopping the watcher is a single command with clear status output
  (running or not, PID, last poll time).

## Out of Scope

- Batch-mode autopilot (`autopilot-batch.md`) — watcher targets single-ticket
  approvals only.
- Changing how `/build`, `/deliver`, or `/write-spec` resolve status beyond
  the new approval signal.
- Notifying the lead of watcher activity outside its own log file.
