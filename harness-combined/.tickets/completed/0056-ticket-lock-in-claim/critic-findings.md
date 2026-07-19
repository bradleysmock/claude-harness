# Critic Findings — 0056-ticket-lock-in-claim

## Round 1 — 2026-07-19

## Critic Report — Ticket 0056-ticket-lock-in-claim (Code Review, Round 1)

**Active panels:** Core (always active) + Python + Testing Strategy. (Files in scope: `ticket.py`, `hooks/ticket_commit_guard.py` — Python; `tests/test_0056_ticket_lock.py` — Testing; `commands/problem.md`, `context/harness-reference.md` — prose docs, no panel trigger.)

**Step 2.5 ticket-baseline checks performed:** requirements-coverage (all 8 FRs and 3 NFRs mapped against implementation + tests), solution.md alignment, weakened/deleted-test check.

---

### Requirements coverage / solution alignment (Step 2.5)

All 8 functional requirements and 3 non-functional requirements have a corresponding implementation and at least one passing test (unit and/or integration), matched against `requirements.md`'s Test Plan. The implementation follows `solution.md`'s architecture precisely: the rename-verify primitive (`_lock_capture`) is shared by steal and release exactly as specified, constants match, `commands/problem.md` and `context/harness-reference.md` changes match the specified component descriptions. No weakened or deleted tests were found; `tests/test_ticket_commit_guard.py` is untouched and the new `IGNORED_STALE_PREFIX` addition is purely additive. No BLOCKER on this dimension.

---

### Findings

**MAJOR** · Core / Dimension 8 (McGraw — fail closed) · `ticket.py:588-609` (`_heartbeat_ticket_lock`), `ticket.py:627-631` (`claim()`'s `build` closure)

When `_heartbeat_ticket_lock` detects lost ownership (a successor stole the lock after a >60s stall), `build()` sets `lock_owned = False`, warns, and then **continues** to compute `number = _next_number(records)` and returns the claim event to `ledger_append` — the mutation still gets built and, in a local-only repo (no remote), written via `git update-ref refs/heads/harness-tickets <new_sha>` with no compare-and-swap (`_tickets_txn`, unchanged by this ticket, at the `if not remote:` branch). This is precisely the scenario `problem.md` identifies as the ticket's core motivation: "In local-only repos... the local lock is the *only* serialization." Once heartbeat loses ownership, a second process is now free to be running its own `_acquire_ticket_lock`/`_tickets_txn` concurrently with the first — and since the local `update-ref` has no old-value check, whichever process's ref write lands last silently discards the other's claim, reproducing the exact double-claim/lost-update bug this ticket exists to eliminate, now gated behind a >60s stall instead of a bare check-then-act. This residual risk is disclosed in `solution.md`'s Risks section ("claim continues with no backstop") and was presumably accepted at Checkpoint 1, but the accepted behavior is fail-*open* where a fail-*closed* alternative is cheap: when `_heartbeat_ticket_lock` returns `False` inside `build()`, raise immediately (a dedicated exception, or re-raise a sentinel) instead of letting `build()` return the event — this aborts `ledger_append`/`_tickets_txn` before any write, propagates through `claim()`'s `finally` (which already correctly skips release), and the caller sees a clean failure instead of a silent lost-update in the local-only case. This is a small, self-contained change to `claim()`'s closure and does not touch `_tickets_txn`, the renumber/push loop, or the lock format (all explicitly out of scope). Recommend re-confirming with the lead whether "warn and continue" or "abort on lost ownership" is the intended tradeoff now that the local-only failure mode is concrete.

**MINOR** · Testing Strategy / Dimension 22 (untested branch) + Requirements alignment · `ticket.py:560-568` (`_acquire_ticket_lock`)

`requirements.md` FR-3 specifies "`FileNotFoundError` at the read or the rename ⇒ vanished ⇒ loop" — i.e., a vanished lock should cause the acquire loop to retry `O_CREAT|O_EXCL` immediately rather than being treated as a live lock. The acquire loop implements this correctly for its *own* read of the main lock file (`lock.read_text()` at line 557, caught by `except FileNotFoundError: continue`), but a vanish detected *inside* `_lock_capture` (its internal `os.rename(lock, temp)` or `temp.read_text()` raising `FileNotFoundError`) returns the same `False` as a genuine rename-verify race loss (a fresh lock recreated by a third process). The caller (lines 564-568) cannot distinguish the two and treats both as "live," incrementing `live_retries` and sleeping 2s even when the lock target is actually gone and an immediate `O_EXCL` retry would very likely succeed. This doesn't break correctness (the loop eventually retries within the 25-iteration/5-live-retry ceiling), but it burns retry budget and adds a needless 2s delay in a multi-contender race, making the ceiling easier to hit adversarially than the "loop immediately" wording implies. Consider having `_lock_capture` distinguish "vanished" from "mismatch" (e.g., a three-way return or a raised sentinel for the vanish case) so the acquire loop can `continue` immediately on vanish, matching FR-3's literal specification.

**MINOR** · Testing Strategy / Dimension 22 (untested critical path) · `ticket.py:556-559`

No test directly exercises the acquire loop's own `except FileNotFoundError: continue` branch (the main `.ticket.lock` file vanishing between the failed `O_CREAT|O_EXCL` and the subsequent `lock.read_text()`). The existing tests (`test_lock_capture_vanished_at_rename_returns_false`, `test_lock_capture_vanished_at_reread_returns_false`) cover vanish scenarios only inside `_lock_capture`'s internal rename/re-read of the *temp*, not this earlier read of the primary lock path inside `_acquire_ticket_lock` itself. A monkeypatched `os.open`/`Path.read_text` sequence (open raises `FileExistsError`, then a concurrent unlink before the read) would close this gap.

No other findings — the lock primitives, staleness/steal/release logic, heartbeat wiring, doc/hook changes, and test suite otherwise match `requirements.md` and `solution.md` faithfully, with no code smells, naming, or decomposition issues rising above OBS level.

### Round 1 resolution

The MAJOR finding was auto-repaired: `claim()`'s `build()` closure now raises a dedicated `_LockOwnershipLost` exception the moment heartbeat detects lost ownership, aborting `ledger_append`/`_tickets_txn` before any ledger write (fail-closed) rather than letting a possibly-racing claim event through. `solution.md`'s Components table and Risks section were updated to match. Two new tests (`test_claim_lost_ownership_mid_build_raises_before_writing`, `test_claim_lost_ownership_writes_nothing_to_ledger`) cover the new behavior; the prior test asserting the old "warn and continue" behavior was replaced.

The two MINOR findings were left for the lead per policy (optional, never auto-fixed).

## Round 2 — 2026-07-19

## Critic Report — Ticket 0056-ticket-lock-in-claim (Code Review, Round 2)

**Active panels:** Core (always active) + Python + Testing Strategy. Files in scope: `ticket.py`, `hooks/ticket_commit_guard.py` (Python); `tests/test_0056_ticket_lock.py` (Testing + Python); `commands/problem.md`, `context/harness-reference.md` (prose, no panel trigger).

**Step 2.5 ticket-baseline checks performed:** MAJOR-fix verification, requirements coverage (all 8 FRs / 3 NFRs), `solution.md` alignment, weakened/deleted-test check.

---

### MAJOR-fix verification (Round 1 finding)

Confirmed correct and complete. `ticket.py:612-620` adds `_LockOwnershipLost(RuntimeError)`; `claim()`'s `build()` closure (`ticket.py:638-646`) now raises it the instant `_heartbeat_ticket_lock` returns `False`, before `_next_number` is called or the claim-event dict is constructed. Traced the call chain: `build()` → `mutate()` (`ticket.py:381-388`, `ledger_append`) → `_tickets_txn` (`ticket.py:352`, `mutate(records)` uncaught) — no code between `build()`'s raise and `_tickets_txn`'s propagation point can write `file_updates`, build a tree, or touch `update-ref`. `claim()`'s `finally` (`ticket.py:665-667`) correctly gates release on `lock_owned`, which is `False` at raise time, so a successor's lock is never touched. Verified with both new tests (`test_claim_lost_ownership_mid_build_raises_before_writing`, `test_claim_lost_ownership_writes_nothing_to_ledger`, `tests/test_0056_ticket_lock.py:430-466`) that the fix is exercised at both the unit (`_heartbeat_ticket_lock` stubbed) and integration (`ledger_append` stubbed, simulated successor write) level, and that the old "warn and continue" test/behavior was fully removed with no dangling references in code. `solution.md`'s Components table (claim() row) and Risks section were updated consistently with the new behavior. No BLOCKER remains on this dimension.

---

### Requirements coverage / solution alignment (Step 2.5)

All 8 FRs and 3 NFRs still have implementation + passing test coverage. `solution.md` and the implementation are consistent with each other post-repair. One drift noted below (OBS) between `requirements.md` and the now fail-closed behavior. No weakened/deleted tests beyond the intentional, disclosed replacement of the round-1 "warn and continue" test with the two new fail-closed tests (this is the correct outcome of a MAJOR repair, not a regression).

---

### Findings

**MINOR** (carried forward from Round 1, unaddressed — left for lead per policy) · Testing Strategy / Dimension 22 + Requirements alignment · `ticket.py:470-499` (`_lock_capture`), `ticket.py:560-563` (caller)

`_lock_capture` still returns the same `False` for a genuine rename-verify mismatch (a fresh lock recreated by a third process — correctly "live") and for a vanish at rename/re-read (`FileNotFoundError`, correctly "gone, retry `O_EXCL` immediately" per FR-3's literal wording). `_acquire_ticket_lock`'s caller (`ticket.py:562-567`) cannot distinguish these and treats both as "live" — incrementing `live_retries` and sleeping 2s even on a vanish, when an immediate loop-and-retry would very likely succeed. Still correctness-safe (bounded by the 25-iteration/5-live-retry ceiling) but burns retry budget unnecessarily and makes the ceiling easier to hit adversarially than FR-3 implies. Unchanged since Round 1; still worth a three-way return (or sentinel) from `_lock_capture` distinguishing vanish from mismatch.

**MINOR** (carried forward from Round 1, unaddressed — left for lead per policy) · Testing Strategy / Dimension 22 (untested critical path) · `ticket.py:556-559`

No test directly exercises `_acquire_ticket_lock`'s own `except FileNotFoundError: continue` at line 558 — the primary `.ticket.lock` vanishing between the failed `O_CREAT|O_EXCL` and the subsequent `lock.read_text()`. Existing vanish tests (`test_lock_capture_vanished_at_rename_returns_false`, `test_lock_capture_vanished_at_reread_returns_false`) only cover vanish *inside* `_lock_capture`'s internal rename/re-read of the temp, not this earlier read of the primary lock path. Still an open gap; a monkeypatched read-then-unlink sequence would close it.

**OBS** · Core / Dimension 4 (documentation) + Requirements/solution consistency · `requirements.md` FR-1 vs. `ticket.py:612-646` / `solution.md`'s updated Components row and Risks section

`requirements.md` FR-1 still reads "on lost ownership stop heartbeating, skip release, warn — never overwrite a successor's lock" — it does not mention the newly added fail-closed abort (raising `_LockOwnershipLost` before the claim event is built). The round-1 repair updated `solution.md` to describe this, but `requirements.md` (the baseline contract document) was left as originally written. The wording isn't contradicted by the fix (FR-1 is silent on whether `claim()` continues or aborts after warning), so this is not a BLOCKER/MAJOR gap, but the two baseline docs are now out of sync on a load-bearing behavior — worth a one-line addendum to `requirements.md` FR-1 the next time it's touched, so a future reader of `requirements.md` alone doesn't believe "warn and continue" is still the contract.

**OBS** · Core / Dimension 4 (documentation) · `ticket.py:623-630` (`claim()` docstring)

`claim()`'s own docstring was not updated to mention that it can raise `_LockOwnershipLost` on lost lock ownership mid-claim. The contract is documented adjacently — directly above, in `_LockOwnershipLost`'s own docstring (`ticket.py:612-620`) — so this is not a functional gap, just a missed opportunity to state the exception in the public function's own contract per Ousterhout's "document preconditions, return value, errors" guidance.

No other findings — the fix is minimal, self-contained, correctly wired through `ledger_append`/`_tickets_txn`'s existing exception-propagation path, does not touch `_tickets_txn`, the renumber/push loop, or the lock format (all out of scope per `problem.md`), and the rest of the lock primitives, staleness/steal/release logic, heartbeat wiring, doc/hook changes, and test suite continue to match `requirements.md` and `solution.md` faithfully.
