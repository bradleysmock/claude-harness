# Solution

**Ticket**: 0075
**Title**: Identity-stamped audit log

## Approach

Add `audit.py`: `record()` appends one JSON line to `.harness/audit.log`
using atomic `O_APPEND|O_CREAT`, resolving identity via `git config
user.name` -> `$USER` -> `getpass.getuser()`. `read()` filters lines by
ticket for display. Call sites are added only at the points a human
actually resolves a decision — not at machine-triggered status transitions.

## Components

| Component | Responsibility | Key interface |
|---|---|---|
| `audit.py` | Append-only log + identity resolution | `record(action, ticket, detail, *, root)`, `read(ticket, *, root)` |
| `commands/deliver.md` | Records on completed merge | `audit.record(action="deliver", ...)` |
| `commands/rollback.md` | Records on completed revert | `audit.record(action="rollback", ...)` |
| `context/flows/build-ticket.md`, `autopilot-ticket.md` | Records when a ticket moves *away from* `changes-requested` (the resolution), not when it's set | `audit.record(action="resolve-pause", ...)` |
| `autopilot-ticket.md` Step B | Records the refine-touched carve-out confirmation | `audit.record(action="confirm-scope-drift", ...)` |
| `commands/ticket-status.md` | Optional trailing "Audit" section per ticket | calls `audit.read(ticket, ...)` |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Plain JSONL, `O_APPEND\|O_CREAT` | Matches `learnings.py`'s existing atomic-append discipline; no read-modify-write race |
| `subprocess.run(["git","config","user.name"], shell=False)` | Matches `gates/config.py`'s existing subprocess-hardening convention |
| No index/cache in `read` | File stays small for a single-operator/small-team harness (stated non-goal: not DB-scale) |
| Fold display into `/ticket-status` rather than a new `/audit` command | Avoids a single-purpose command for read-only display of existing data; `read()` stays independently usable later |

## Decisions (resolves source doc's Checkpoint-1 questions)

- **Commit vs. gitignore**: gitignore `.harness/audit.log`, matching
  `.harness/memory.db`'s existing precedent. Committing would put local
  usernames in shared history and produce constant merge noise across
  worktrees/branches for an append-only file with no merge semantics;
  the non-goal already rules out a tamper-proof/DB-backed trail, so a
  local-only file is proportionate.
- **Which transitions warrant a line**: only ones a human actively
  decided — `/deliver`, `/rollback`, resolving a `changes-requested`
  pause, and Step B's scope-drift confirmation. **Correction to the source
  doc**: it cited "autopilot-ticket.md Step B" for the exhausted-repair
  escalation decision — that's wrong on two counts. First, Step B is
  auto-deliver, not the escalation halt (Step A is). Second, neither Step
  A's nor `build-ticket.md` Step 7d's *setting* of `changes-requested` is
  itself a human decision — it's the machine escalating after exhausted
  repair. The actual human decision happens later, when the lead resumes
  `/build` or runs `/review` and the ticket moves *off*
  `changes-requested` — that's the call site (FR-9), not the point where
  it's set (FR-8 explicitly excludes it). Step B's own genuine synchronous
  decision — the refine-touched carve-out confirmation — is a distinct,
  previously-uncited call site (FR-10).
- **New command vs. folded display**: fold into `/ticket-status XXXX` as
  an optional trailing section, shown only when entries exist for that
  ticket.
- **Future `pause_for_human` policy dispositions** (`[[2026-09-03-data-driven-promotion-policy-design]]`):
  no separate call site needed — that pause resolves through the same
  `/build` resume or `/review` path FR-9 already covers.

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1/2/3    | Unit        | `record` writes a well-formed line; identity fallback chain |
| FR-4        | Integration | Two concurrent `record` calls, both lines intact |
| FR-5/11     | Unit        | `read` filters by ticket; tolerates missing/corrupt file |
| FR-6        | Integration | `/deliver XXXX` produces exactly one new line |
| FR-7        | Integration | `/rollback XXXX` produces exactly one new line |
| FR-8/9      | Integration | Setting `changes-requested` logs nothing; resolving it logs one line |
| FR-10       | Integration | Refine-touched carve-out confirmation logs `confirm-scope-drift` |

## Tradeoffs

- **Gitignored over committed**: loses the record if the machine is wiped,
  in exchange for no username-in-history exposure and no merge noise.
- **Resolve-time logging over set-time logging**: slightly harder to wire
  (must detect "was this ticket previously `changes-requested`?" at the
  point of transition) but correctly attributes the decision to the person
  who made it, not the automation that escalated.

## Risks

- Missing the exact point `build-ticket.md`/`autopilot-ticket.md` next
  writes `status.md` after a `changes-requested` resume would silently
  drop FR-9's audit line — mitigated by a dedicated integration test
  (Test Plan row above) rather than relying on code review alone.
- `git config user.name` unset in CI/sandboxed environments — covered by
  the fallback chain (FR-2) and its own unit test.

## Implementation Order

1. Failing unit tests for `record`/`read` (FR-1-5,11); implement `audit.py`.
2. Failing integration test for concurrent writers (FR-4); verify under
   `PIPE_BUF`.
3. Failing integration tests + wire `commands/deliver.md`,
   `commands/rollback.md` (FR-6,7).
4. Failing integration test + wire the `changes-requested` resolution call
   site in `build-ticket.md`/`autopilot-ticket.md` (FR-8,9), and Step B's
   scope-drift confirmation (FR-10).
5. Add the optional Audit section to `commands/ticket-status.md`.
6. Document the log format and gitignore status in
   `context/harness-reference.md`.
