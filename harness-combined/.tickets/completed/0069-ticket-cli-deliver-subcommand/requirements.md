# Requirements

**Ticket**: 0069
**Title**: Ticket CLI deliver subcommand

## Functional Requirements

1. `ticket.py`'s `_main()` must accept a `deliver` command taking a single
   positional `<ticket-id>` argument and no `--push` flag: `deliver_squash`
   always publishes `main` unconditionally, matching `deliver-batch`'s
   existing no-push-flag shape.
2. `deliver` must resolve `<ticket-id>` to a full slug, branch, and title via
   `_resolve_claim` (the ledger-based lookup `cancel`/`abandon`/`reopen`
   already use), then read `status.md` via `_read_ticket_docs`'s existing
   worktree-or-branch-ref fallback — never a new filesystem-only resolver,
   and never `repo/.tickets/` directly, which has no entry for an in-flight
   ticket under the `harness-tickets` ledger model. If `_read_ticket_docs`
   returns no `status.md` entry (a claimed ticket with no readable docs),
   `deliver` must raise `FileNotFoundError` explicitly rather than let a
   `KeyError` escape from indexing the missing key.
3. The `deliver` command must call `deliver_squash(repo, branch, slug, title)`
   with the resolved values and print its returned commit subject on success,
   matching `deliver-batch`'s existing pattern of printing each result.
4. `status.md` must be `review-ready` before `deliver` proceeds; any other
   status must cause a non-zero exit with a message naming the actual status,
   never a silent no-op or a delivery of an unfinished ticket.
5. Any `RuntimeError` from `deliver_squash` — a rejected push, or a
   `git merge --squash` conflict (`git()` always raises `RuntimeError` after
   inspecting the return code; it never lets `subprocess.CalledProcessError`
   escape) — must be caught at the CLI boundary, reported to stderr, and
   leave the worktree/branch intact, never an uncaught traceback.
6. `ticket.py deliver` with a missing `<ticket-id>` must print a usage
   message and exit **2**, matching `_main()`'s existing missing-positional
   convention. An ident `_resolve_claim` can't find must be caught
   (`FileNotFoundError`) and reported with exit **1** — never a traceback.

## Non-Functional Requirements

1. No new dependency; reuse existing `deliver_squash`/`_resolve_claim` and
   `argv` parsing conventions already present in `ticket.py`.

## Test Strategy

| Type       | Rationale                                                        |
|------------|-------------------------------------------------------------------|
| Unit       | CLI-dispatch level: `deliver` routes to `deliver_squash` with the correct resolved args; non-`review-ready` status rejected; missing ticket-id rejected; `RuntimeError`/conflict surfaced as non-zero exit, not swallowed. |
| Integration| End-to-end against a fixture repo (mirroring existing `deliver_squash` tests): claim → build a fake `review-ready` ticket → `ticket.py deliver <id>` → assert the squash commit, archive, and ledger `delivered` event, matching what `deliver_squash` already proves, but invoked via the CLI entry point. |

## Acceptance Criteria

- `python3 ticket.py deliver 0069-some-slug` on a `review-ready` fixture
  ticket produces one squash commit and prints its subject — no manual
  `python3 -c` invocation needed.
- `deliver` on a non-`review-ready` ticket exits non-zero, untouched repo.
- `ticket.py deliver` (no id) exits 2 with a usage message; an unresolvable
  id exits 1 — neither ever tracebacks.

## Open Questions

None.
