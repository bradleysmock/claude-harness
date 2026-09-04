# Requirements

**Ticket**: 0075
**Title**: Identity-stamped audit log

## Functional Requirements

1. The system must provide `audit.py` (sibling to `memory.py`/`learnings.py`)
   with `record(action, ticket, detail, *, root) -> None` and
   `read(ticket, *, root) -> list[dict]`.
2. `record` must resolve identity via `subprocess.run(["git", "config",
   "user.name"], shell=False, ...)`, falling back to `os.environ.get("USER")`
   then `getpass.getuser()` when git config is unset.
3. `record` must append one JSON line (`ts`, `who`, `action`, `ticket`,
   `detail`) to `.harness/audit.log`, opened with `os.O_APPEND |
   os.O_CREAT` — no read-modify-write window.
4. Two processes calling `record` in quick succession must each produce one
   intact, non-interleaved line (append-only, under `PIPE_BUF`).
5. `read` must filter recorded lines by `ticket` (or return all when
   `ticket=None`) without building an index or cache.
6. `commands/deliver.md` must call `audit.record(action="deliver", ...)` as
   its last step on a completed merge.
7. `commands/rollback.md` must call `audit.record(action="rollback", ...)`
   as its last step on a completed revert.
8. `context/flows/build-ticket.md` Step 7d and `autopilot-ticket.md` Step A
   must **not** call `audit.record` when they set `status: changes-requested`
   — that transition is machine-triggered by repair exhaustion, not a human
   decision (see `solution.md § Decisions`, correcting the source design's
   citation of "Step B" for this point — Step B is auto-deliver, not the
   escalation halt, and neither step's own transition is itself a resolved
   human choice).
9. Whichever flow next moves a ticket's `status.md` away from
   `changes-requested` (a resumed `/build XXXX`, or `commands/review.md`
   reaching an approval) must call `audit.record(action="resolve-pause",
   ...)` — this is the actual human-decided moment the source doc's Problem
   statement means by "a resolved gate pause."
10. `autopilot-ticket.md` Step B's refine-touched carve-out confirmation
    (the lead confirming delivery despite a machine-adjusted scope) must
    call `audit.record(action="confirm-scope-drift", ...)`.
11. `read(ticket, root=...)` must return entries in file order (oldest
    first) without raising on a missing `.harness/audit.log`.

## Non-Functional Requirements

1. No new service or database; a single JSONL file under `.harness/`.
2. `record`'s subprocess call uses an argv list (`shell=False`), matching
   `gates/config.py`'s existing subprocess hardening convention.
3. A missing/corrupt single line in `audit.log` must not prevent `read`
   from returning the other well-formed lines.

## Test Strategy

| Type        | Rationale                                                   |
|-------------|--------------------------------------------------------------|
| Unit        | `record` writes one well-formed line; identity fallback chain |
| Unit        | `read` filters by ticket; tolerates a missing/corrupt file    |
| Integration | Concurrent `record` calls produce non-interleaved lines       |
| Integration | `/deliver` and `/rollback` each produce exactly one new line  |

## Acceptance Criteria

- `record` writes a line with the resolved git identity, no git config ->
  falls back to `USER`, then `getpass.getuser()`.
- Two concurrent `record` calls never corrupt or interleave either line.
- `/deliver XXXX` and `/rollback XXXX` each produce exactly one new
  `audit.log` line naming the operator and the ticket id.
- Setting `changes-requested` produces no audit line; resolving it does.

## Open Questions

None — the three checkpoint questions from the source design doc (commit vs.
gitignore `audit.log`, which transitions warrant a line, new command vs.
folded-in display) are resolved as design decisions in
`solution.md § Decisions`, for lead confirmation at Checkpoint 1.
