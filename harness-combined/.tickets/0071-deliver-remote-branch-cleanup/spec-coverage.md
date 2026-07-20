# Spec Coverage Map

**Ticket**: 0071-deliver-remote-branch-cleanup
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | `ticket.py::deliver_squash`'s cleanup (currently inline `git worktree | 0071-deliver-remote-branch-cleanup-ticket-py |
| FR-2 | FR | The replacement in FR-1 must sit inside the existing | 0071-deliver-remote-branch-cleanup-ticket-py |
| FR-3 | FR | `ticket.py::deliver_squash_batch`'s three inline cleanup sites (batch | 0071-deliver-remote-branch-cleanup-ticket-py |
| FR-4 | FR | The remote delete is skipped cleanly when no remote exists, via | 0071-deliver-remote-branch-cleanup-ticket-py |
| FR-5 | FR | A failed/rejected remote-branch delete must not abort delivery or touch the | 0071-deliver-remote-branch-cleanup-ticket-py |
| AC-1 | AC | Delivering a ticket (solo or batch) against a fixture remote leaves no | 0071-deliver-remote-branch-cleanup-ticket-py |
| AC-2 | AC | A remote-delete failure is non-fatal; a rejected `main` push still leaves | 0071-deliver-remote-branch-cleanup-ticket-py |
| AC-3 | AC | All pre-existing tests pass unmodified. | 0071-deliver-remote-branch-cleanup-ticket-py |
| FR-6 | FR | `context/flows/deliver-ticket.md` Step 4c's prose documents the corrected | — |
| FR-7 | FR | `commands/ticket-status.md`/`skills/stale/SKILL.md`/`skills/status/SKILL.md` | — |

## Uncovered

- FR-6 (FR): `context/flows/deliver-ticket.md` Step 4c's prose documents the corrected
- FR-7 (FR): `commands/ticket-status.md`/`skills/stale/SKILL.md`/`skills/status/SKILL.md`
