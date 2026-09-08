# Design: Identity-stamped audit log

**Date:** 2026-09-03
**Status:** Proposed (not yet ticketed)
**Author:** Bradley + Claude
**Origin:** Comparison against agentic-dev-platform, which records the OS-account
identity of the operator on every gate resolution and approval decision. A grep of
harness-combined for `getuser`/`git config user.name`/`GIT_AUTHOR` turned up
nothing — no decision in this harness is currently attributed to anyone.

## Problem

Approve/reject-type decisions — `/deliver`, `/rollback`, a resolved gate pause —
leave no record of who made the call. On a shared machine, or when a delivered
ticket is disputed later, there's nothing to check against.

## Goal

Every human-facing decision point appends one line to a local, append-only audit
log naming who made the call — no new service, no database, a JSONL file under
`.harness/`.

## Non-goals

- A tamper-proof or cryptographically signed log (the platform's audit trail
  lives in a database with its own access controls; this is a plain local file,
  proportionate to a single-operator or small-team harness).
- Attributing *every* ticket status transition — only the ones a human actively
  decided (see Open Decisions).

## Architecture

### `audit.py` (new, sibling to `memory.py` / `learnings.py`)

```python
def record(action: str, ticket: str, detail: str, *, root: Path) -> None: ...
def read(ticket: str | None, *, root: Path) -> list[dict]: ...
```

`record` resolves identity via `subprocess.run(["git", "config", "user.name"], ...)`
(argv list, `shell=False` — the same hardening convention `gates/config.py`
already applies to every subprocess call in this codebase), falling back to
`os.environ.get("USER")` then `getpass.getuser()` if git config is unset. It
appends one JSON line to `.harness/audit.log`:

```json
{"ts": "2026-09-03T14:02:11Z", "who": "bradley", "action": "deliver", "ticket": "0071", "detail": "merged to main"}
```

The write opens with `os.O_APPEND | os.O_CREAT`, matching the atomic-append
discipline `learnings.py` already uses for `_learnings.md` — no read-modify-write
window, safe under concurrent writers up to `PIPE_BUF`.

`read` is a thin filter over the file for display (`/status`, or a new
`/audit XXXX`) — no index, no cache; the file is expected to stay small enough
to scan directly for a single-operator or small-team harness.

### Call sites

**Correction (2026-09-03):** an earlier draft of this list treated
"a resolved gate pause" as hypothetical, contingent on the promotion-policy
design landing. It isn't — the harness already has two pause points, they're
just unattributed today:

- `changes-requested` — set by `/build` Step 7d or the `review` skill when the
  lead requests changes; cleared when the lead re-runs `/build` after
  addressing them.
- The exhausted-repair escalation decision in `autopilot-ticket.md` Step B —
  the lead picks among the options presented after `repair-escalation.md`
  returns `"exhausted"`.

Any flow that currently changes ticket status or resolves one of these on a
human decision calls `audit.record(...)` as its last step:

- `commands/deliver.md` — on merge.
- `commands/rollback.md` — on revert.
- `commands/review.md` / `context/flows/build-ticket.md` Step 7d — when the
  lead sets or clears `changes-requested`.
- `autopilot-ticket.md` Step B — whichever option the lead picks after an
  exhausted-repair escalation.
- The `pause_for_human` disposition in
  [[2026-09-03-data-driven-promotion-policy-design]], once that lands — it
  routes through the same escalation halt as the point above, so no separate
  call site is needed.

This mirrors the platform's "operator identity recorded on every gate
resolution" pattern, as a flat file instead of a DB column.

## Files to change

- `audit.py` — new.
- `commands/deliver.md`, `commands/rollback.md`, `commands/review.md`,
  `context/flows/build-ticket.md`, `context/flows/autopilot-ticket.md` — add
  the `record` call at each point a human decision resolves a status or a
  pause.
- `.gitignore` — decide whether `.harness/audit.log` is tracked (see Open
  Decisions).
- `context/harness-reference.md` — document the log's location and format.
- `tests/test_audit.py` — new.

## Verification

1. **Basic append**: `record` writes one well-formed JSON line with the
   resolved git identity.
2. **Fallback chain**: with git config unset, `USER` env var is used; with
   neither, `getpass.getuser()` is used.
3. **Concurrent writers**: two processes calling `record` in quick succession
   produce two intact, non-interleaved lines (append-only under `PIPE_BUF`).
4. **Integration**: running `/deliver XXXX` in a test fixture produces exactly
   one new audit line naming the current git user and the ticket id.

## Open decisions for Checkpoint 1

1. Is `.harness/audit.log` committed (a durable team record, closest to the
   platform's DB-backed trail) or gitignored (local-only, like
   `.harness/memory.db`)? Committing exposes local usernames in history;
   gitignoring loses the record if the machine is wiped.
2. Which actions warrant a line — every ticket status transition, or only the
   ones a human actively decided (deliver, rollback, approve/reject on a
   pause)? Logging every transition is more complete but dilutes the signal
   for "who decided what."
3. Should `/audit XXXX` be a new command, or folded into the existing
   `/ticket-status` / `/status` output as an optional trailing section?
