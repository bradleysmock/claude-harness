# Solution

**Ticket**: 0075
**Title**: Identity-stamped audit log

## Approach

Add `audit.py`: `record()` appends one JSON line to `.harness/audit.log`
via a single `os.write()` on `O_APPEND|O_CREAT`, identity resolved
`git config user.name` -> `$USER` -> `getpass.getuser()` -> `"unknown"`.
`read()` filters by ticket. Call sites sit at the exact step a human
decision resolves, correcting several wrong citations in the source doc.

## Components

| Component | Responsibility |
|---|---|
| `audit.py` | Append-only log + identity resolution |
| `deliver-ticket.md` Step 4c, `rollback/SKILL.md` Step 11 | Record only on the actual completion branch |
| `build-ticket.md` Steps 1/6, `review/SKILL.md` approved branch | Record a resolved `changes-requested` pause |
| `autopilot-ticket.md` Step B, `cancel/abandon/reopen.md` | Record their lead-confirmed decisions |
| `commands/ticket-status.md` | Per-ticket argument + trailing Audit section |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Single `os.write()`, not buffered `.write()` | `O_APPEND` non-interleaving holds only per syscall |
| `subprocess.run([...], shell=False)` | Matches `gates/python.py` (not `gates/config.py`, which has no subprocess calls) |
| Fail-open identity (`who="unknown"`) | Logging failure must never look like the real op failed |
| Fold display into `/ticket-status` | Avoids a single-purpose command |

## Decisions (resolves source doc's Checkpoint-1 questions + corrections)

- **Commit vs. gitignore**: gitignore, matching `.harness/memory.db` — no
  usernames in history, no merge noise on an append-only file.
- **Which transitions warrant a line**: `deliver`, `rollback`,
  `resolve-pause`, `confirm-scope-drift`, `cancel`/`abandon`/`reopen` —
  every lead-confirmed decision (last three widen the source list,
  flagging for sign-off); a future `pause_for_human` policy disposition
  needs no separate site, since it resolves through the same path.
- **New command vs. folded display**: folded into `/ticket-status XXXX`.
- **Corrected call sites**: source doc cited empty dispatchers
  (`deliver.md`/`rollback.md`; real points are `deliver-ticket.md`
  Step 4c, `rollback/SKILL.md` Step 11), a nonexistent
  `commands/review.md`, and "Step B" for changes-requested (that's the
  escalation, Step 7d/A — resolution is Step 6 / review's approved branch).

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1/2/3    | Unit/Integ. | Correct write; identity fallback incl. all-fail -> `unknown`; concurrent calls stay intact |
| FR-4        | Unit        | `read` filters by ticket; skips one bad line among good ones |
| FR-5        | Integration | Deliver logs only after Step 4c; Step 4b auto-revert logs none |
| FR-6        | Integration | Rollback logs only on Step 11's commit branch |
| FR-7        | Integration | `changes-requested` set logs nothing; resolve logs one line |
| FR-8        | Integration | Scope-drift + cancel/abandon/reopen each log one line |
| FR-9        | Integration | `/ticket-status XXXX` shows Audit section only when entries exist |

## Tradeoffs / Risks

- **Gitignored over committed**: loses the record on a wiped machine, for
  no username exposure or merge noise.
- **Resolve-time over set-time logging**: needs a resume flag threaded
  Step 1 -> Step 6 (risk: easy to drop later — mitigated by the FR-7
  test, not code review alone). Unset `git config user.name` in CI is
  covered by the fallback chain.

## Implementation Order

1. Failing unit tests for `record`/`read` (FR-1-4); implement `audit.py`,
   incl. concurrent-writer test (FR-3).
2. Failing integration tests + wire `deliver-ticket.md` Step 4c (FR-5) and
   `rollback/SKILL.md` Step 11 (FR-6).
3. Failing integration test + wire the Step 1/6 resume flag and
   `review/SKILL.md`'s approved branch (FR-7).
4. Wire `autopilot-ticket.md` Step B and `cancel/abandon/reopen.md` (FR-8);
   add the ticket-argument + Audit section to `ticket-status.md` (FR-9).
5. Document format, gitignore status, call sites in `harness-reference.md`.
