# Solution

**Ticket**: 0078
**Title**: Standalone autopilot watcher on lead approval

## Approach

Add two optional `status.md` fields, written only on Checkpoint 1 "yes":
`approved-at` (display date) and `approved-commit` (HEAD *before* the
approval-write commit — i.e. the last design commit). `status` stays
`solution`, so every existing check keeps working unmodified. A background
loop, started/stopped independently of any Claude Code session, polls
worktrees for `solution` + `approved-commit` tickets. Before dispatch it
fail-closes on three checks: `approved-commit` is a valid SHA shape, is an
ancestor of the branch's current HEAD, and `problem.md`/`requirements.md`/
`solution.md` are byte-identical between that SHA and HEAD (a scoped `git
diff --quiet`) — content drift since approval means "not approved," never
"build anyway." Raw `HEAD == approved-commit` is impossible by construction
(the approval-write commit is a descendant of the SHA it records), which is
why the gate is a content-diff, not an equality check. On a pass, the tick
logs `(ticket, approved-commit)`, then blocks on `claude -p "/autopilot
XXXX"` until it exits — so at most one build is ever in flight.

## Components

| Component | Responsibility |
|---|---|
| `commands/problem.md` Checkpoint 1 | On "yes": commit+push both fields; note mentions the watcher |
| `autopilot_watch.py` | Scan/validate/filter, ancestor+content-diff gate, commit-keyed dispatch log, PID lifecycle (mirrors `ticket.py`'s `_pid_alive`), blocking dispatch (injectable), process-group stop |
| `bin/autopilot-watch` | Thin argv shim to `autopilot_watch.py`, matching `bin/ticket` |
| `commands/autopilot-watch.md` | Lead-facing docs: `start\|stop\|status` |
| `context/harness-reference.md` | Additive docs for the two fields + watcher mechanism |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| New fields, not a new `status` value | Zero blast radius on existing status checks |
| Content-diff gate over raw commit equality | The only form that's actually implementable — approval always precedes its own recording commit — while still fail-closing on real drift |
| Blocking dispatch inside the tick | Trivially satisfies "one build at a time" — no separate lock/semaphore |
| PID/lifecycle in Python, `bin/*` as a thin shim | Matches `bin/ticket`; reuses `ticket.py`'s tested staleness pattern |
| `nohup`+`sleep` loop, own process group | Portable, no OS-specific setup; owning its process group lets `stop` reach an in-flight `claude -p` child, traded against launchd/cron's free crash auto-restart (see Risks) |

## Test Plan

| Requirement | Test Type   | Scenario(s)                                                        |
|-------------|-------------|---------------------------------------------------------------------|
| FR-1/FR-2   | Doc-wiring  | `problem.md` documents both fields; `status: solution` unchanged   |
| FR-3        | Unit        | malformed directory name rejected before reaching a dispatch prompt |
| FR-4        | Unit (real sequence) | replay design-commit → field-write-commit → dispatch passes; a further edit to `solution.md` after approval → skipped, logged |
| FR-5/FR-6   | Unit        | same-day reopen+re-approve dispatches (new SHA); log write precedes dispatch call; tick blocks until dispatch returns |
| FR-7        | Integration | `stop` mid-dispatch terminates the child via process-group signal; log entry stays "dispatched," no crash, no auto-retry |
| FR-8/FR-9   | Unit + Integration | PID staleness reused from `ticket.py` pattern; double `start` refused; `stop` idempotent; `status` reports outcome/exit code, including "interrupted" |
| FR-10       | Unit        | a raising tick is caught, logged, loop continues next interval      |

## Tradeoffs

- **Chose a content-diff gate over a stronger cryptographic/session-signed
  approval because**: this plugin has no auth primitive anywhere else
  (ownership is already `git config user.email` by convention); content-diff
  closes the concrete "drift after approval" gap cheaply without inventing a
  new trust model unique to this feature.
- **Chose a lead-local watcher over a shared/multi-developer one because**:
  the worktree model is per-machine; shared watching needs new coordination.
- **Accepting risk of**: no OS-level crash supervision for the loop process
  itself — FR-10's per-tick catch covers in-loop errors, not the outer
  `nohup` process dying from an unhandled signal.

## Risks

- `stop` during an in-flight build has no automatic retry — documented, not
  silently swallowed; the lead reruns `/autopilot XXXX` manually if needed.
- Headless `claude -p` permission profile must allow autopilot's build/git
  operations unattended, scoped to the dispatched ticket's own worktree,
  passed explicitly (never inherited ambient settings) — mismatch is visible
  via `status`'s exit-code field.
- Poll interval: default 30s, configurable via `--interval`.

## Implementation Order

1. Unit tests for `autopilot_watch.py` (scan/validate/filter, ancestor+diff
   gate incl. the real-sequence case, commit-keyed log, PID liveness,
   blocking dispatch) — red first.
2. Implement `autopilot_watch.py` to pass them.
3. `bin/autopilot-watch` thin shim; integration tests for start/stop/status,
   including stop-mid-dispatch.
4. `commands/problem.md` Checkpoint 1 field writes + note.
5. `commands/autopilot-watch.md`; doc-wiring tests for both command files.
6. `context/harness-reference.md` additive documentation.
