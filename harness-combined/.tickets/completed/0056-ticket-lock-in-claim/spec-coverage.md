# Spec Coverage Map

**Ticket**: 0056-ticket-lock-in-claim
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-7 | FR | `commands/problem.md` Phase 1 must consist of the single `ticket.py claim` | 0056-ticket-lock-in-claim-problem-doc |
| FR-1 | FR | `ticket.py` `claim()` must acquire `.tickets/.ticket.lock` itself via | — |
| FR-2 | FR | A lock must count as stale when its epoch is over 60s old, its pid is dead | — |
| FR-3 | FR | Stealing must be verified: `os.rename` the lock to | — |
| FR-4 | FR | Live locks must retry up to 5 times with a 2-second sleep; a total-iteration | — |
| FR-5 | FR | Release must run in a `finally` on every `claim()` exit path, never raise | — |
| FR-6 | FR | Each acquisition loop entry must self-heal orphaned `.ticket.lock.stale-*` | — |
| FR-8 | FR | The lock path and `pid:epoch` format must remain unchanged — | — |
| AC-1 | AC | Two interleaved acquisitions never both hold the lock, incl. the | — |
| AC-2 | AC | Live lock ⇒ non-zero exit naming the holder pid; stale lock ⇒ stolen, proceeds. | — |
| AC-3 | AC | After success or raise no self-owned lock remains; exceptions propagate unmasked. | — |
| AC-4 | AC | `commands/problem.md` Phase 1 has no `.ticket.lock` Bash; existing tests pass. | — |

## Uncovered

- FR-1 (FR): `ticket.py` `claim()` must acquire `.tickets/.ticket.lock` itself via
- FR-2 (FR): A lock must count as stale when its epoch is over 60s old, its pid is dead
- FR-3 (FR): Stealing must be verified: `os.rename` the lock to
- FR-4 (FR): Live locks must retry up to 5 times with a 2-second sleep; a total-iteration
- FR-5 (FR): Release must run in a `finally` on every `claim()` exit path, never raise
- FR-6 (FR): Each acquisition loop entry must self-heal orphaned `.ticket.lock.stale-*`
- FR-8 (FR): The lock path and `pid:epoch` format must remain unchanged —
- AC-1 (AC): Two interleaved acquisitions never both hold the lock, incl. the
- AC-2 (AC): Live lock ⇒ non-zero exit naming the holder pid; stale lock ⇒ stolen, proceeds.
- AC-3 (AC): After success or raise no self-owned lock remains; exceptions propagate unmasked.
- AC-4 (AC): `commands/problem.md` Phase 1 has no `.ticket.lock` Bash; existing tests pass.
