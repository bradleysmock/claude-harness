# Requirements

**Ticket**: 0075
**Title**: Identity-stamped audit log

## Functional Requirements

1. The system must provide `audit.py`: `record(action, ticket, detail, *,
   root) -> None`, `read(ticket, *, root) -> list[dict]`.
2. `record` must resolve identity via `git config user.name` (argv
   `subprocess.run`, `shell=False`, matching `gates/python.py`), then
   `$USER`, then `getpass.getuser()`, writing `who="unknown"` if all fail.
3. `record` must `mkdir(parents=True, exist_ok=True)` on `.harness/`,
   then write the JSON line + newline as one `os.write()` on an
   `O_APPEND|O_CREAT` descriptor, not a buffered `.write()`.
4. `read` must filter by `ticket` (`None` = all), skip an unparseable
   line instead of raising, and return `[]` for a missing file.
5. `deliver-ticket.md` Step 4c (publish/cleanup), not Step 4/4b, must
   call `record(action="deliver", ...)` — a Step-4b smoke-test
   auto-revert must produce no line.
6. `rollback/SKILL.md` Step 11 must call `record(action="rollback", ...)`
   only on the branch that commits a revert, not the no-op early exit.
7. `build-ticket.md` Step 7d / `autopilot-ticket.md` Step A must not call
   `record` on setting `changes-requested` (machine escalation, not a
   human decision); Step 1 must flag a resumed `changes-requested`, and
   Step 6 (and `review/SKILL.md`'s no-op "approved" branch) must call
   `record(action="resolve-pause", ...)` when that flag is set.
8. `autopilot-ticket.md` Step B's refine-touched confirmation, and
   `commands/cancel.md`/`abandon.md`/`reopen.md` after their
   lead-confirmed transaction succeeds, must each call `record` with a
   matching `action`.
9. `commands/ticket-status.md` must accept an optional ticket argument
   (none exists today) and show its `read()` entries as a trailing
   "Audit" section when any exist.

## Non-Functional Requirements

1. No new service/database; one JSONL file under `.harness/`.
2. One malformed line must not block `read` from returning the rest.
3. Identity-resolution failure is fail-open (FR-2) — an accountability aid, not access control.

## Test Strategy

| Type        | Rationale                                           |
|-------------|-------------------------------------------------------|
| Unit        | fallback chain incl. all-fail; bad-line skip in `read` |
| Integration | non-interleaved writers; deliver/rollback fire at the right step; pause set vs. resolved |

## Acceptance Criteria

- Fallback chain works end to end; all-fail writes `who="unknown"`.
- Concurrent `record` calls never corrupt or interleave.
- `/deliver` logs only after 4c (a smoke-test revert logs nothing);
  `/rollback` logs only when a revert actually commits.
- Setting `changes-requested` logs nothing; resolving it logs one line;
  `/cancel`, `/abandon`, `/reopen` each log one line on success.

## Open Questions

None — resolved as decisions in `solution.md § Decisions`.
