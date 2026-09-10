Manage the standalone autopilot approval watcher: a background process that
dispatches `/autopilot XXXX` automatically once a ticket clears Checkpoint 1
approval, without needing a `/problem` or `/build` session to stay open.

## Subcommands

`/autopilot-watch start [--interval N]` — refuses to start a second loop
while one is already running (PID-liveness check). Default poll interval:
30 seconds. Each poll dispatches at most one ticket and blocks until that
`/autopilot` invocation exits — builds never run concurrently from the watcher.

`/autopilot-watch stop` — signals the running loop's whole process group; an
in-flight dispatch is terminated within a grace period. A no-op (not an
error) if nothing is running. The interrupted ticket's dispatch-log entry is
not rolled back — rerun `/autopilot XXXX` manually if the build didn't finish.

`/autopilot-watch status` — reports running/not, PID, last tick time, and
the last dispatch's outcome (including an interrupted or errored dispatch).

## What it dispatches

A ticket is picked up only when its `status.md` has `status: solution`
**and** a non-blank `approved-commit` (written by `/problem`'s Checkpoint 1
on the lead's "yes" — see `commands/problem.md`) that still passes a
fail-closed content-diff gate: `approved-commit` must be a valid SHA, an
ancestor of the branch's current HEAD, and `problem.md`/`requirements.md`/
`solution.md` must be byte-identical between that commit and HEAD. Any
drift since approval — a later commit touching the design files — is
treated as "not approved" and skipped, never built.

## Scope

Single-ticket only — batch-mode autopilot (`/autopilot XXXX + YYYY`) is
never targeted. Local-worktree only: the watcher polls `.worktrees/*` on the
machine it runs on, not a shared, multi-developer view. Manual `/autopilot
XXXX` behaves identically whether or not the watcher is running.
