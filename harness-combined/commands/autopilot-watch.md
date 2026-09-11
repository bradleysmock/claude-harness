Manage the standalone autopilot approval watcher: a background process that
dispatches `/autopilot XXXX` automatically once a ticket clears Checkpoint 1
approval, without needing a `/problem` or `/build` session to stay open.

## Steps

1. Parse `$ARGUMENTS` for the subcommand — `start`, `stop`, or `status` — and,
   for `start` only, an optional `--interval N`.
2. Run `bin/autopilot-watch <subcommand> . [--interval N]` (`.` is the
   project root containing `.harness/` and `.worktrees/` — the directory this
   command is invoked from) and show its stdout/stderr to the lead verbatim.
3. Report the exit code as-is — a non-zero exit (e.g. `start` refusing a
   second run) is the answer, not an error to retry or suppress.

## Subcommands

`/autopilot-watch start [--interval N]` — refuses to start a second loop
while one is already running (PID-liveness check). Default poll interval:
30 seconds. Each poll dispatches at most one ticket and blocks until that
`/autopilot` invocation exits — builds never run concurrently from the watcher.

`/autopilot-watch stop` — signals the running loop's whole process group; an
in-flight dispatch is terminated within a grace period. A no-op (not an
error) if nothing is running. The interrupted ticket's dispatch-log entry is
not rolled back — rerun `/autopilot XXXX` manually if the build didn't finish.

`/autopilot-watch status` — reports running/not, PID, last tick time, the
last dispatch's outcome (including an interrupted or errored dispatch), and a
needs-attention summary: how many dispatches have ended in a state that wants
the lead, plus the most recent one's ticket and reason.

## When a dispatch needs attention

After each dispatch returns, the watcher re-reads the target ticket's
`status.md` and classifies the outcome from that file alone — never from log
or stdout text. `status: done` is success. Anything else needs attention:
`changes-requested` (repair exhausted), an unmoved `solution` (a score-spec
bail), a build stuck at `implementing` or `review-ready`, a `status.md` that
became unreadable mid-build (a concurrent `/cancel`, `/abandon`, or
`/deliver`), or a dispatch that failed to launch at all.

Every needs-attention outcome goes two places:

- **A durable log** — one JSON line per outcome appended to
  `.harness/autopilot-watch/needs-attention.jsonl`, carrying the ticket,
  the reason, the observed status, and a timestamp. This is the record of
  last resort: append-only, never overwritten, greppable.
- **A desktop notification** — `osascript` on macOS, `notify-send` on Linux.
  This is **best-effort** by design: if neither tool is present, or the
  notification fails, the tick carries on and the log still has the entry.
  Never rely on the notification alone.

## Watching via Claude (`/loop`)

For a conversational channel instead of an OS notification, run the `/loop`
skill in an interactive Claude Code session alongside the watcher. No extra
code or configuration — `/loop` takes an interval and a prompt:

```
/loop 10m Run `bin/autopilot-watch status` in the project root. If the
needs-attention count went up since your last check, tell me which ticket
and why in one line, and suggest the next step. If nothing changed, say so
in one line and stop.
```

The loop reads the same `needs-attention.jsonl` that `status` summarizes, so
it reports the same facts the desktop notification would have — but in a
session where the lead can immediately ask a follow-up or hand the ticket
straight to `/review XXXX` or `/build XXXX`.

Pick an interval longer than a typical build so a single ticket isn't
reported as "still going" on every tick. `/loop` with no interval lets the
model pace itself, which is usually the better default here.

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
