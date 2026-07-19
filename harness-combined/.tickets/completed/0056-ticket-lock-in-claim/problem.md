# Problem Statement

**Ticket**: 0056
**Title**: Move ticket lock into ticket.py claim (atomic acquire/release)
**Date**: 2026-07-12

## Problem

`/problem` Phase 1 has the agent run the `.tickets/.ticket.lock` protocol as ad hoc
Bash: an existence check followed by a write (check-then-act, not atomic), plus
staleness/pid logic re-implemented from prose on every run. Any `ticket.py claim`
invoked outside `/problem` gets no locking at all.

## Impact

- Two same-machine agents (concurrent autopilots are routine here) can interleave
  the check and the write and both proceed — double-claiming a number.
- In local-only repos (no `--push`), the push race never arbitrates: both claims
  commit to `main`, producing duplicate numbers and index contention. The local
  lock is the *only* serialization — and it is the least reliable piece.
- Prose-driven lock logic drifts per session; a mistake deletes a live lock.

## Success Criteria

- `ticket.py claim` acquires the lock itself via atomic `O_CREAT|O_EXCL`, holding
  it across number scan, commit, push/renumber, and branch/worktree creation.
- Stale locks (>60s old, dead pid, or malformed) are stolen safely (atomic
  rename, not unlink-in-place); live locks retry then fail with a clear error.
- The lock is released on every exit path, only by its owner.
- `commands/problem.md` Phase 1 shrinks to the single `claim` call.
- Lock path and `pid:epoch` format unchanged — `cancel`/`abandon` crash cleanup
  and `ticket_commit_guard` continue to work untouched.
- Unit tests cover exclusivity, steal, conflict, and release paths.

## Out of Scope

- Cross-machine arbitration (the claim-push race handles that, unchanged).
- Changing the renumber/push loop, lock path, or lock format.
- Migrating other sentinel files (`.tickets/.active`).
