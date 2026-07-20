# Spec Coverage Map

**Ticket**: 0055-refine-touched-flag-persist
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | `context/spec-remediation.md` S2 must write a marker file `refine-touched.md` | — |
| FR-2 | FR | `context/flows/autopilot-ticket.md` Step S must describe the mark as the | — |
| FR-3 | FR | `context/flows/autopilot-ticket.md` Step B must decide the carve-out by | — |
| FR-4 | FR | `context/flows/deliver-ticket.md` must resolve the marker from the branch's | — |
| FR-5 | FR | `ticket.py` `_fold_archive` must delete `refine-touched.md` from the archived | — |
| FR-6 | FR | `ticket.py` `deliver_squash_batch` must probe every member **before the first | — |
| FR-7 | FR | `context/flows/autopilot-batch.md` must exclude marker-carrying members at | — |
| FR-8 | FR | The marker filename must be the single literal `refine-touched.md` everywhere. | — |
| AC-1 | AC | `deliver_squash` over a ticket dir with the marker → `completed/` dir without | — |
| AC-2 | AC | `deliver_squash_batch` with a marker member in any position → raises before the | — |
| AC-3 | AC | All four docs contain the literal `refine-touched.md`; Step B / deliver / batch | — |

## Uncovered

- FR-1 (FR): `context/spec-remediation.md` S2 must write a marker file `refine-touched.md`
- FR-2 (FR): `context/flows/autopilot-ticket.md` Step S must describe the mark as the
- FR-3 (FR): `context/flows/autopilot-ticket.md` Step B must decide the carve-out by
- FR-4 (FR): `context/flows/deliver-ticket.md` must resolve the marker from the branch's
- FR-5 (FR): `ticket.py` `_fold_archive` must delete `refine-touched.md` from the archived
- FR-6 (FR): `ticket.py` `deliver_squash_batch` must probe every member **before the first
- FR-7 (FR): `context/flows/autopilot-batch.md` must exclude marker-carrying members at
- FR-8 (FR): The marker filename must be the single literal `refine-touched.md` everywhere.
- AC-1 (AC): `deliver_squash` over a ticket dir with the marker → `completed/` dir without
- AC-2 (AC): `deliver_squash_batch` with a marker member in any position → raises before the
- AC-3 (AC): All four docs contain the literal `refine-touched.md`; Step B / deliver / batch
