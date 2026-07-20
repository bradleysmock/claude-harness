# Requirements

**Ticket**: 0070
**Title**: Status/stale ledger-sourced ticket discovery + nesting-aware worktree join

## Functional Requirements

1. `ticket.py` gets one shared helper, `_worktree_ticket_dir(repo, worktree,
   slug)`, computing the offset-corrected `.tickets/<slug>` path once; every
   site building a worktree-relative ticket-dir path uses it —
   `_create_branch_and_worktree`, `list_tickets`, `reopen`, `_read_ticket_docs`.
2. The offset (`_project_offset`, git top-level to `repo`, auto-detected via
   `git rev-parse --show-toplevel`, no manual config) is empty for a flat repo,
   keeping all four sites byte-identical to current behavior there.
3. `claim()` offset-corrects the stub write, `git add` pathspec, and
   idempotent-resume check together, via the shared helper.
4. `list_tickets()`'s worktree join reads via the shared helper (offset computed
   once outside its per-ticket loop), falling back to the pre-fix path when the
   corrected one has no `status.md`.
5. `reopen()` and `_read_ticket_docs()` (cancel/abandon) use the shared helper —
   both currently reproduce claim's exact pre-fix bug.
6. `_project_offset` raises the module's `RuntimeError` convention (matching
   `git()`), never a bare `ValueError`, off the git top-level.
7. `list_tickets()`'s output surfaces `updated` (parsed already, dropped today).
8. `status/SKILL.md` Step 1 and `stale/SKILL.md`'s shared block enumerate via
   `ticket.py list-json` as an embedded primary source, scan-fallback only when
   unreachable; both files end byte-identical there — a deliberate
   simplification of, not a mirror of, `ticket-list.md`'s scan-wins merge (FR-7
   makes `list-json` alone sufficient).
9. A newly-claimed nested-project ticket appears in `/status` immediately —
   covered by FR-3+FR-4+FR-8's tests, no separate end-to-end test needed.

## Non-Functional Requirements

1. Flat-repo behavior byte-identical to pre-fix (existing suite unmodified).
2. Offset computed once per invocation (bounded `git()` call-count test); no new
   dependencies — `pathlib` + the existing `git()` helper only.

## Test Strategy

| Type       | Rationale                                                        |
|------------|--------------------------------------------------------------------|
| Unit       | Offset: flat → empty; nested → correct; outside ancestry → `RuntimeError`. |
| Unit       | Shared helper used identically by all 4 call sites, nested fixture. |
| Unit       | `list_tickets()`: corrected read, pre-fix fallback, single `git()` call. |
| Unit       | Embedded `list-json` script + byte-equality of the two SKILL.md files' block. |
| Regression | `tests/test_ticket_module.py` flat-repo cases pass unmodified. |

## Acceptance Criteria

- Claim, reopen, and doc-snapshot (cancel/abandon) in a nested fixture all
  resolve to the real project dir — no stray root-level dir, ever; resuming an
  already-claimed nested ticket never duplicates the stub.
- `list-json` reports the ticket's true worktree status and `updated`.
- `status/SKILL.md`/`stale/SKILL.md` byte-identical in the shared block (test-verified); all pre-existing flat-repo ticket tests pass unmodified.

## Open Questions

None — verified this session: all 8 live legacy worktrees already sit at the corrected path; FR-4's fallback is forward-looking safety only.
