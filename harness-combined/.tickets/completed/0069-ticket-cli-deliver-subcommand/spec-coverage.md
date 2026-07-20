# Spec Coverage Map

**Ticket**: 0069-ticket-cli-deliver-subcommand
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | `ticket.py`'s `_main()` must accept a `deliver` command taking a single | — |
| FR-2 | FR | `deliver` must resolve `<ticket-id>` to a full slug, branch, and title via | — |
| FR-3 | FR | The `deliver` command must call `deliver_squash(repo, branch, slug, title)` | — |
| FR-4 | FR | `status.md` must be `review-ready` before `deliver` proceeds; any other | — |
| FR-5 | FR | Any `RuntimeError` from `deliver_squash` — a rejected push, or a | — |
| FR-6 | FR | `ticket.py deliver` with a missing `<ticket-id>` must print a usage | — |
| AC-1 | AC | `python3 ticket.py deliver 0069-some-slug` on a `review-ready` fixture | — |
| AC-2 | AC | `deliver` on a non-`review-ready` ticket exits non-zero, untouched repo. | — |
| AC-3 | AC | `ticket.py deliver` (no id) exits 2 with a usage message; an unresolvable | — |

## Uncovered

- FR-1 (FR): `ticket.py`'s `_main()` must accept a `deliver` command taking a single
- FR-2 (FR): `deliver` must resolve `<ticket-id>` to a full slug, branch, and title via
- FR-3 (FR): The `deliver` command must call `deliver_squash(repo, branch, slug, title)`
- FR-4 (FR): `status.md` must be `review-ready` before `deliver` proceeds; any other
- FR-5 (FR): Any `RuntimeError` from `deliver_squash` — a rejected push, or a
- FR-6 (FR): `ticket.py deliver` with a missing `<ticket-id>` must print a usage
- AC-1 (AC): `python3 ticket.py deliver 0069-some-slug` on a `review-ready` fixture
- AC-2 (AC): `deliver` on a non-`review-ready` ticket exits non-zero, untouched repo.
- AC-3 (AC): `ticket.py deliver` (no id) exits 2 with a usage message; an unresolvable
