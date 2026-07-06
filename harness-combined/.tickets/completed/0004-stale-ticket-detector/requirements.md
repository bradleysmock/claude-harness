# Requirements

**Ticket**: 0004
**Title**: Stale ticket detector

## Functional Requirements

1. The system must provide a `/stale` command that scans `.tickets/*/status.md` (excluding `completed/`) and identifies tickets whose `updated:` date field is older than the idle threshold.
2. The system must display each stale ticket with: ticket number, title, current status, and integer days idle (calculated as today's date minus `updated:` date).
3. The system must default the idle threshold to 7 days when no override is configured.
4. The system must allow the idle threshold to be overridden via a `--days N` flag passed to `/stale`.
5. The system must allow the idle threshold to be configured in `_standards.md` via a `stale_threshold_days` key, which takes lower precedence than the `--days` flag.
6. The system must output "No stale tickets" (or equivalent) when no tickets exceed the threshold.
7. The `/status` skill output must include a stale summary line (e.g., "2 stale tickets — run /stale to see details") when one or more tickets exceed the threshold; the summary must be omitted when no tickets are stale.
8. The system must handle missing or malformed `updated:` fields gracefully (skip with a logged warning rather than crashing).

## Non-Functional Requirements

1. The command must complete in under 2 seconds for up to 100 tickets on a standard developer machine.
2. Date parsing must treat `updated:` values as YYYY-MM-DD strings; timezone-naive comparison against the local system date is acceptable.

## Test Strategy

| Type        | Rationale                                           |
|-------------|-----------------------------------------------------|
| Unit        | Threshold logic, date-diff calculation, flag/config precedence, missing-field handling |
| Integration | End-to-end scan of a mock `.tickets/` tree with a mix of fresh, stale, and malformed entries |

## Acceptance Criteria

- `/stale` with no flags returns only tickets where `(today - updated) > 7`.
- `/stale --days 3` returns only tickets idle more than 3 days.
- A `stale_threshold_days: 14` key in `_standards.md` raises the default to 14; `--days 5` still overrides to 5.
- A ticket with a missing `updated:` field is skipped and does not cause an error.
- `/status` output includes a stale-ticket count line when stale tickets exist and omits it when none exist.
- All unit and integration tests pass.

## Open Questions

- None.
