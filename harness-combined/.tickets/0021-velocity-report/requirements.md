# Requirements

**Ticket**: 0008
**Title**: Ticket velocity report

## Functional Requirements

1. The system must scan `.tickets/completed/*/status.md` files to discover all completed tickets.
2. The system must extract the `updated` date from each completed ticket's `status.md` as the completion date.
3. The system must extract the creation date from each completed ticket's `problem.md` (`**Date**` field, format `YYYY-MM-DD`) as the start date (proxy for when the ticket entered active work — the authoring date, not a status-transition timestamp).
4. The system must compute cycle time in days (completion date − start date) for each completed ticket using a deterministic date library (Python `datetime.date` or equivalent shell arithmetic via `date` commands), not LLM inference.
5. The system must group tickets by ISO week of their completion date and display a trend table with columns: Week, Tickets, Avg Cycle Time (days), Min, Max.
6. The system must display a per-ticket detail table: Ticket, Title, Start, Done, Cycle Time (days).
7. The system must display an overall average cycle time across all completed tickets.
8. The system must handle the case of zero completed tickets gracefully with a clear message.
9. The system must handle missing or malformed `updated` / `**Date**` fields gracefully, skipping affected tickets and reporting skipped count. Date fields must match `YYYY-MM-DD`; any other format is treated as malformed.
10. The system must handle negative cycle time (end date earlier than start date) by skipping the affected ticket and incrementing the skip counter with a "invalid date range" note.
11. The system must validate that every path produced by the `.tickets/completed/*/` glob scan resolves (via `Path.resolve()`) to a path under the harness root before opening it; any path that escapes the harness root must be silently skipped.
12. The system must pass ticket data to `compute.py` via stdin (not as a shell argument) to prevent injection from attacker-influenced date or slug values.
13. The system must be invokable as a slash command `/velocity` from the harness (manual verification only; not a CI-tested scenario).

## Non-Functional Requirements

1. The command must complete in under 2 seconds for up to 200 completed tickets.
2. Output must be plain-text Markdown tables, readable in the terminal and in Claude's rendered output.

## Tech Stack

Not applicable — this is a new skill/command added to the existing harness plugin (Markdown-driven, no new runtime dependency).

## Date Format Contract

- `problem.md` start date: extracted via `\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})` — any other format is malformed.
- `status.md` completion date: extracted via `updated:\s*(\d{4}-\d{2}-\d{2})` — any other format is malformed.
- ISO week grouping must use ISO 8601 semantics (e.g., 2021-01-01 is week 53 of 2020, not week 1 of 2021).

## Test Strategy

| Type        | Rationale                                                      |
|-------------|----------------------------------------------------------------|
| Unit        | Cycle-time calculation (including zero-day and negative); date-parsing edge cases including malformed input; ISO week grouping including year-boundary (2021-01-01 vs 2021-01-04) |
| Integration | End-to-end scan of a fixture `.tickets/completed/` tree (3+ tickets, 2+ weeks); verify both tables and overall avg; empty-dir case; negative-cycle-time skip case |

## Acceptance Criteria

- `/velocity` with no completed tickets prints "No completed tickets found." and exits cleanly.
- `/velocity` with 3+ completed tickets spanning 2+ weeks produces both the per-ticket table and the weekly summary table.
- Tickets with a missing or malformed `**Date**` or `updated` field are skipped; the report notes the skip count.
- Tickets with negative cycle time (end < start) are skipped with "invalid date range" noted in the skip count.
- Avg cycle time in the weekly summary matches manual calculation from the per-ticket detail table for the same fixture.
- ISO week grouping is correct across the year boundary (2021-01-01 in W53-2020, 2021-01-04 in W01-2021).
- Output contains no stack traces or internal paths on any error path.
- Cycle time for fixture pair `(2026-01-01, 2026-01-11)` always equals exactly 10 days (determinism assertion).

## Open Questions

- None. Timestamps from `status.md` (`updated`) and `problem.md` (`Date`) are sufficient; git log is a fallback but not required for MVP.
