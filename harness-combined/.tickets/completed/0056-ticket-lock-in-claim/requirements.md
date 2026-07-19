# Requirements

**Ticket**: 0056
**Title**: Move ticket lock into ticket.py claim (atomic acquire/release)

## Functional Requirements

1. `ticket.py` `claim()` must acquire `.tickets/.ticket.lock` itself via
   `os.open(path, O_CREAT|O_EXCL|O_WRONLY)` writing `pid:epoch` (integer epoch),
   before the number scan; hold it across stub write, commit, push/renumber, and
   branch/worktree creation; and heartbeat — rewrite `pid:epoch` each renumber
   iteration only after re-reading the lock and confirming the pid field is its
   own; on lost ownership stop heartbeating, skip release, warn — never
   overwrite a successor's lock.
2. A lock must count as stale when its epoch is over 60s old, its pid is dead
   (`ProcessLookupError` from `os.kill(pid, 0)`; `PermissionError` = alive), or
   its content is malformed — non-integer fields or pid ≤ 0 (never `os.kill`ed).
3. Stealing must be verified: `os.rename` the lock to
   `.ticket.lock.stale-<own-pid>`, re-read the temp, compare with the observed
   stale content — match ⇒ unlink temp and loop to `O_EXCL`; mismatch (a fresh
   lock was renamed) ⇒ restore non-clobberingly (`os.link(temp, lock)` then
   unlink temp; `FileExistsError` ⇒ unlink temp, lock is live) and treat as
   live. `FileNotFoundError` at the read or the rename ⇒ vanished ⇒ loop.
4. Live locks must retry up to 5 times with a 2-second sleep; a total-iteration
   ceiling of 25 must bound every loop path. Exhaustion raises `RuntimeError`
   naming the holder pid and lock path — "unknown holder" plus the raw content
   when the last observation is unparseable — and the CLI exits non-zero.
5. Release must run in a `finally` on every `claim()` exit path, never raise
   (missing lock ⇒ no-op, read error ⇒ leave in place), and be owner-checked via
   the same rename-verify primitive — foreign content renamed back untouched.
6. Each acquisition loop entry must self-heal orphaned `.ticket.lock.stale-*`
   temps whose **filename-suffix** pid is dead: restore the content via the
   non-clobbering link when its content pid is alive, else unlink the temp.
7. `commands/problem.md` Phase 1 must consist of the single `ticket.py claim`
   call — manual acquire/release steps removed; a note says the lock is built in.
8. The lock path and `pid:epoch` format must remain unchanged —
   `cancel.md`/`abandon.md` cleanup stays valid unmodified;
   `ticket_commit_guard.py`'s IGNORED set gains one `.ticket.lock.stale-` prefix
   entry; `harness-reference.md`'s lock line must note claim manages it.

## Non-Functional Requirements

1. With no contention, `claim`'s observable git behavior is byte-identical to today.
2. Touched Python passes the gate's exact lint/type checks (no new findings).
3. Tests must not depend on wall-clock sleeps (patch sleep/time/os.kill).

## Test Strategy

| Type        | Rationale                                                        |
|-------------|------------------------------------------------------------------|
| Unit        | Lock loop in isolation: `O_EXCL` exclusivity; stale-epoch / dead-pid / malformed (incl. pid ≤ 0, float epoch) steal; verify-after-rename restores a fresh lock and treats it live; vanished lock at read or rename loops; live lock raises after 5 sleeps; ceiling raises at 25 iterations; release is a no-op on missing lock, preserves a primary exception, leaves foreign locks intact; orphaned stale-temp with dead pid is reaped. |
| Integration | `claim()` in tmp git repos: lock held during body, absent after success and after a forced raise; heartbeat rewrites epoch each renumber round; `commands/problem.md` content-verification (single call, no manual lock Bash). |

## Acceptance Criteria

- Two interleaved acquisitions never both hold the lock, incl. the
  fresh-lock-renamed race (restored non-clobberingly, treated live).
- Live lock ⇒ non-zero exit naming the holder pid; stale lock ⇒ stolen, proceeds.
- After success or raise no self-owned lock remains; exceptions propagate unmasked.
- `commands/problem.md` Phase 1 has no `.ticket.lock` Bash; existing tests pass.
