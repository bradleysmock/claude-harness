# Requirements

**Ticket**: 0070
**Title**: Status/stale ledger-sourced ticket discovery + nesting-aware worktree join

## Functional Requirements

1. `ticket.py` must compute each worktree's project-relative offset (git
   top-level to `repo`, auto-detected via `git rev-parse --show-toplevel`, no
   manual config) once per invocation, applied to every worktree/ticket-dir path
   it constructs; empty offset (flat repo) keeps current behavior byte-identical.
2. `claim()` must offset-correct the stub write, the `git add` pathspec, and the
   idempotent-resume existence check together — not the stub write alone.
3. `list_tickets()`'s worktree join must read from the offset-corrected path,
   offset computed once outside its per-ticket loop, falling back to the
   pre-fix path when the corrected one has no `status.md`.
4. `_project_offset` must raise the module's `RuntimeError`-with-context
   convention (matching `git()`), never a bare `ValueError`, when `repo` isn't
   under the git top-level.
5. `list_tickets()`'s output must surface `updated` (already parsed, currently
   dropped) so `list-json` is a complete source for `/status`.
6. `status/SKILL.md` Step 1 and `stale/SKILL.md`'s shared block must both
   enumerate via `ticket.py list-json` as an embedded (not prose) primary
   source, falling back to a legacy `.tickets/*` scan only when unreachable —
   mirroring `ticket-list.md`; the two files end byte-identical in that block,
   reconciling `stale/SKILL.md`'s current ambiguous-precedence wording.
7. A newly-claimed nested-project ticket appears in `/status`'s Active Tickets
   table immediately, before any design artifact exists.

## Non-Functional Requirements

1. Flat-repo behavior byte-identical to pre-fix — existing test suite passes
   unmodified.
2. Offset computed once per invocation, not per path join — bounded `git()`
   invocation-count test.
3. No new dependencies; pure `pathlib` + the existing `git()` helper.

## Test Strategy

| Type       | Rationale                                                        |
|------------|--------------------------------------------------------------------|
| Unit       | Offset helper: flat → empty; nested → correct; outside ancestry → `RuntimeError`. |
| Unit       | `claim()` on a nested fixture: stub, `git add`, resume-check all at corrected path. |
| Unit       | `list_tickets()`: corrected-path read, pre-fix fallback, single `git()` call regardless of count. |
| Unit       | Embedded `list-json`-union script in both SKILL.md files, tested like `ticket-list.md`'s. |
| Regression | `tests/test_ticket_module.py` flat-repo cases pass unmodified. |

## Acceptance Criteria

- Claiming in a nested fixture writes and commits `status.md` under the real
  project dir — no stray root-level dir.
- Resuming an already-claimed nested ticket never duplicates the stub.
- `list-json` reports the ticket's true worktree status and `updated`.
- `status/SKILL.md`/`stale/SKILL.md` are byte-identical in the shared block.
- All pre-existing flat-repo ticket tests pass unmodified.

## Open Questions

None. Verified this session: all 8 live legacy worktrees already sit at the
corrected nested path — FR-3's fallback is a forward-looking safety net only.
