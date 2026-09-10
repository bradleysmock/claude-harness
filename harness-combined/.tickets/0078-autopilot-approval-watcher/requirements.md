# Requirements

**Ticket**: 0078
**Title**: Standalone autopilot watcher on lead approval

## Functional Requirements

1. `/problem`'s Checkpoint 1, on "yes" only, commits+pushes `approved-at:
   YYYY-MM-DD` (display) + `approved-commit: <sha>` — HEAD at approval time,
   i.e. the last design commit, *before* this approval-write commit itself.
   "no"/"feedback" leave both blank.
2. Purely additive: `status` stays `solution` (unchanged) — `/build`,
   `/write-spec`, `/deliver`, manual `/autopilot` need no change.
3. `autopilot_watch.py` scans `.worktrees/*/.tickets/*/status.md`, validates
   each directory name against the ticket pattern before use, and filters to
   `status: solution` with a non-blank `approved-commit`.
4. Fail-closed dispatch gate: `approved-commit` must match a hex-SHA shape,
   be an ancestor of the branch's current HEAD, **and** `problem.md` /
   `requirements.md` / `solution.md` must be byte-identical between
   `approved-commit` and HEAD (scoped `git diff --quiet`). Any failure —
   invalid shape, not an ancestor, or content drift since approval — skips
   and logs the ticket; never builds on a mismatch. (Raw `HEAD ==
   approved-commit` is impossible: the approval-write commit is itself a
   descendant of the SHA it records, so equality would never hold.)
5. Dispatch log is keyed by `(ticket, approved-commit)` — a `/reopen` +
   same-day re-approval gets a new SHA and dispatches.
6. Dispatch is blocking: the tick logs the entry, then invokes and waits for
   `claude -p "/autopilot XXXX"` to exit before returning; the outer loop
   only sleeps/re-polls after that, so at most one build is ever in flight.
7. `stop` signals the watcher's whole process group (SIGTERM, then SIGKILL
   after a grace period). An in-flight dispatch is terminated; its log entry
   stays marked dispatched with no auto-retry — documented limitation, rerun
   `/autopilot XXXX` manually if the build didn't finish.
8. PID-liveness/staleness logic lives in Python, mirroring `ticket.py`'s
   `_pid_alive`/stale-lock pattern; `bin/autopilot-watch` is a thin
   argv-forwarding shim, matching `bin/ticket`.
9. `start [--interval N]` refuses a second run while a PID is alive; `stop`
   is a no-op if nothing is running; `status` reports running/not, PID, last
   tick time, and last dispatch outcome (best-effort `try/finally`; a killed
   dispatch records "interrupted" where the signal is caught in time).
10. A tick that raises is caught and logged; the loop continues next interval.
11. A new `/autopilot-watch` command documents `start`/`stop`/`status`.
12. `commands/problem.md`'s Checkpoint 1 note mentions the watcher.

## Non-Functional Requirements

1. Watcher state (PID, dispatch log, last-tick/last-error) is on-disk only.
2. All git/shell calls use argument lists, never string-interpolated shells.
3. The `claude -p` subprocess call is injectable for unit testing.

## Test Strategy

| Type        | Rationale                                                          |
|-------------|---------------------------------------------------------------------|
| Unit        | scan/validate/filter; ancestor+content-diff gate (both pass → dispatch; drift after approval → skip); commit-keyed log; log-before-invoke; PID liveness |
| Unit (real sequence) | replay the actual two-commit approval flow (design commit, then the field-write commit) and assert dispatch proceeds — not a synthetic HEAD==approved-commit fixture |
| Doc-wiring  | `problem.md` documents both fields; `autopilot-watch.md` documents all subcommands |
| Integration | start/stop/status against a tmp repo with an injected fake dispatch; stop mid-dispatch terminates the child without crashing the loop |

## Acceptance Criteria

- Approving Checkpoint 1 persists both fields; declining/feedback does not.
- Content drift in the design files after approval blocks dispatch (fail closed).
- Two approvals never build concurrently — the second waits for the first's blocking tick.
- Reopen+re-approve same day still dispatches (new SHA).
- Manual `/autopilot XXXX` is unchanged when the watcher isn't running.
- `stop` terminates an in-flight build within its grace period; that ticket is not auto-retried.
- `/autopilot-watch status` reports running state, PID, last tick time, last dispatch outcome.

## Open Questions

- None — local-worktree-only scope; multi-developer shared watching and
  cryptographic approval signing are out of scope.
