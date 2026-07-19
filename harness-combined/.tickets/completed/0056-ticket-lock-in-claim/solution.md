# Solution

**Ticket**: 0056
**Title**: Move ticket lock into ticket.py claim (atomic acquire/release)

## Approach

Add lock helpers to `ticket.py` and wrap `claim()` in acquire → `try/finally`
release. Acquisition is atomic (`O_CREAT|O_EXCL`); steals and release both go
through one **rename-verify** primitive: rename the lock to a per-pid temp,
re-read, and only act if the content matches what was observed — otherwise
rename it back. `commands/problem.md` Phase 1 collapses to the single `claim`
call. Lock path, format, and crash-cleanup semantics are unchanged.

## Components

| Component | Change |
|-----------|--------|
| `ticket.py` — constants | `_LOCK_STALE_SECONDS=60`, `_LOCK_LIVE_RETRIES=5`, `_LOCK_SLEEP_SECONDS=2`, `_LOCK_MAX_ITERATIONS=25`. |
| `ticket.py` — `_lock_capture(lock, expected)` | The rename-verify primitive: `os.rename(lock, temp=".ticket.lock.stale-<own-pid>")`, re-read temp; content == `expected` ⇒ unlink temp, return True; mismatch ⇒ restore non-clobberingly — `os.link(temp, lock)` + unlink temp, `FileExistsError` ⇒ unlink temp only (a third process holds the path) — return False; `FileNotFoundError` anywhere ⇒ return False. Shared by steal and release. |
| `ticket.py` — `_acquire_ticket_lock(tickets_root)` | mkdir root; loop (≤25 iterations): reap orphaned `.ticket.lock.stale-*` temps whose **filename-suffix** pid is dead (content pid alive ⇒ restore via the non-clobber link, else unlink); try `O_CREAT\|O_EXCL\|O_WRONLY`, write `f"{os.getpid()}:{int(time.time())}"` ⇒ done. On `FileExistsError`: read content (`FileNotFoundError` ⇒ loop); stale/dead/malformed (pid ≤ 0 or non-integer ⇒ malformed, never `os.kill`ed) ⇒ `_lock_capture(observed)` then loop; live ⇒ `time.sleep(2)`, ≤5 live rounds. Exhaustion ⇒ `RuntimeError` naming holder pid + path ("unknown holder" + raw content when unparseable). |
| `ticket.py` — `_release_ticket_lock(tickets_root)` | Never raises: read current content — pid field == own pid ⇒ `_lock_capture(current)` (removes it); else/missing/error ⇒ no-op, so the `finally` can never mask the primary exception. |
| `ticket.py` — `claim()` | Acquire before `next_number`; heartbeat at the top of each renumber iteration — re-read the lock, rewrite `pid:epoch` **only if the pid field is its own**; on lost ownership stop heartbeating, set a skip-release flag, warn to stderr, and raise `_LockOwnershipLost` before the claim event is built (fail-closed — no ledger write on a stolen lock). Release in `finally`. Git behavior otherwise untouched on the no-contention path. |
| `commands/problem.md` | Phase 1 steps 1/3 deleted; single step runs `ticket.py claim` with a note that it serializes same-machine claims via `.tickets/.ticket.lock`; non-zero exit reports the conflict (holder pid in message). |
| `context/harness-reference.md` | Lock line notes acquire/release live in `ticket.py claim` (path/format unchanged). |
| `hooks/ticket_commit_guard.py` | IGNORED gains one `.tickets/.ticket.lock.stale-` prefix entry so a leaked temp never blocks unrelated commits before the next claim reaps it. |
| `tests/test_0056_ticket_lock.py` | Unit + integration + content-verification per the Test Plan. |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Keep the `O_EXCL` sentinel, not `fcntl.flock` | `cancel`/`abandon` cleanup, `ticket_commit_guard` IGNORED set, harness-reference docs, and the 60s staleness convention all key on file existence + `pid:epoch`; `flock` silently changes crash semantics for all of them. |
| Rename-**verify** steal, not bare rename or unlink | Unlink-in-place deletes a fresh lock recreated after the staleness read; bare rename has the same flaw one step later. Verifying the temp against the observed content and restoring on mismatch means at most one process ever treats a given lock instance as stolen. |
| Release through the same primitive | Owner check + removal share the verified path, closing the release TOCTOU for free; release is specified never-raising so a `finally` can't mask the real error. |
| Iteration ceiling on the whole loop | Steal/malformed/rename-loser paths otherwise spin unbounded (e.g. mutual re-steal); one constant converts livelock into the same clear `RuntimeError`. |
| Module-level `time`/`os.kill` calls | Directly monkeypatchable — NFR-3's no-wall-clock tests need no extra seams. |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit + Integration | Lock exists with `pid:int-epoch` during a stubbed `claim` body; heartbeat rewrites epoch each renumber round (patched `time.time`); heartbeat is a no-op — and release is skipped — after a foreign lock replaces ours. |
| FR-2        | Unit        | Stale epoch, dead pid (patched `os.kill` → `ProcessLookupError`), `PermissionError` = alive, float epoch / `0:...` / garbage = malformed and never `os.kill`ed. |
| FR-3        | Unit        | Verify-after-rename: temp matches ⇒ stolen + acquired; temp mismatches ⇒ link-restored, treated live; link `FileExistsError` ⇒ temp unlinked, lock left to the third process; vanish at read/rename ⇒ loop and acquire. |
| FR-4        | Unit        | Live lock: exactly 5 patched sleeps then `RuntimeError` naming holder pid; adversarial loop hits the 25-iteration ceiling and raises. |
| FR-5        | Integration | Lock absent after success; forced mid-claim raise propagates unmasked with lock released; missing-lock release no-op; foreign lock left intact. |
| FR-6        | Unit        | Temp with dead filename pid + dead content pid ⇒ unlinked; dead filename pid + live content pid ⇒ restored to the lock path; live filename pid ⇒ untouched. |
| FR-7        | Integration | `commands/problem.md`: no manual lock Bash, single `claim` call, built-in-lock note. |
| FR-8        | Integration | Path/format literals unchanged; guard ignores a `.ticket.lock.stale-*` path; `harness-reference.md` notes claim-managed lock; existing `ticket.py` tests green. |

## Tradeoffs

- **Chose in-process locking over doc-driven Bash because**: atomicity and
  guaranteed release cannot be enforced from prose, and every `claim` caller
  gets serialization for free.
- **Accepting**: pid recycling can make a dead holder look alive — the 60s epoch
  bound still reclaims the lock within one staleness window.

## Risks

- Concurrency is tested deterministically (patched `os.kill`/`time`, direct
  state setup), not with real races. One disclosed residual window: three
  contenders racing a stale lock can leave one displaced lock (non-clobber
  link degrades it from silent double-hold). Lost ownership after a >60s
  stall is fail-closed (post-critic-review revision): heartbeat detects it,
  warns, and `claim()` raises before any ledger write — in a local-only repo
  `update-ref` has no compare-and-swap, so a claim built after losing
  ownership could otherwise race a concurrent successor's own claim.
- 0055 also edits `ticket.py` (disjoint functions) and may touch
  `harness-reference.md` — trivial textual conflicts; rebase chase at delivery.

## Implementation Order

1. Tests first: `tests/test_0056_ticket_lock.py`.
2. `ticket.py`: constants + `_lock_capture` + `_acquire_ticket_lock` +
   `_release_ticket_lock`, wire into `claim()` with heartbeat + `try/finally`.
3. `commands/problem.md` Phase 1 rewrite.
4. `context/harness-reference.md` lock-line note.
