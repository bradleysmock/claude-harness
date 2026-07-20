# Spec Coverage Map

**Ticket**: 0070-status-stale-ledger-source-nested-worktree
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | `ticket.py` gets one shared helper, `_worktree_ticket_dir(repo, worktree, | — |
| FR-2 | FR | The offset (`_project_offset`, git top-level to `repo`, auto-detected via | — |
| FR-3 | FR | `claim()` offset-corrects the stub write, `git add` pathspec, and | — |
| FR-4 | FR | `list_tickets()`'s worktree join reads via the shared helper (offset computed | — |
| FR-5 | FR | `reopen()` and `_read_ticket_docs()` (cancel/abandon) use the shared helper — | — |
| FR-6 | FR | `_project_offset` raises the module's `RuntimeError` convention (matching | — |
| FR-7 | FR | `list_tickets()`'s output surfaces `updated` (parsed already, dropped today). | — |
| FR-8 | FR | `status/SKILL.md` Step 1 and `stale/SKILL.md`'s shared block enumerate via | — |
| FR-9 | FR | A newly-claimed nested-project ticket appears in `/status` immediately — | — |
| AC-1 | AC | Claim, reopen, and doc-snapshot (cancel/abandon) in a nested fixture all | — |
| AC-2 | AC | `list-json` reports the ticket's true worktree status and `updated`. | — |
| AC-3 | AC | `status/SKILL.md`/`stale/SKILL.md` byte-identical in the shared block (test-verified); all pre-existing flat-repo ticket tests pass unmodified. | — |

## Uncovered

- FR-1 (FR): `ticket.py` gets one shared helper, `_worktree_ticket_dir(repo, worktree,
- FR-2 (FR): The offset (`_project_offset`, git top-level to `repo`, auto-detected via
- FR-3 (FR): `claim()` offset-corrects the stub write, `git add` pathspec, and
- FR-4 (FR): `list_tickets()`'s worktree join reads via the shared helper (offset computed
- FR-5 (FR): `reopen()` and `_read_ticket_docs()` (cancel/abandon) use the shared helper —
- FR-6 (FR): `_project_offset` raises the module's `RuntimeError` convention (matching
- FR-7 (FR): `list_tickets()`'s output surfaces `updated` (parsed already, dropped today).
- FR-8 (FR): `status/SKILL.md` Step 1 and `stale/SKILL.md`'s shared block enumerate via
- FR-9 (FR): A newly-claimed nested-project ticket appears in `/status` immediately —
- AC-1 (AC): Claim, reopen, and doc-snapshot (cancel/abandon) in a nested fixture all
- AC-2 (AC): `list-json` reports the ticket's true worktree status and `updated`.
- AC-3 (AC): `status/SKILL.md`/`stale/SKILL.md` byte-identical in the shared block (test-verified); all pre-existing flat-repo ticket tests pass unmodified.
