# Requirements

**Ticket**: 0035
**Title**: Sprint Planning Command

## Functional Requirements

1. The system must scan all open tickets under `.tickets/*/status.md` (excluding `completed/`) to collect tickets to plan, and also scan `.tickets/completed/*/status.md` to identify pre-satisfied dependencies. Each ticket's `effort` field (`small`, `medium`, `large`) and `depends-on` field (comma-separated ticket numbers) are extracted using `grep -m1 "^field:" | cut -d: -f2-` with `set -euo pipefail`; no `eval` or `ls` parsing.
2. The system must map effort labels to numeric point values: `small=1`, `medium=2`, `large=3`. Tickets with no `effort` field are treated as `medium` (2 points) with a visible warning in the output.
3. The system must accept a `--sprint-capacity` option (integer, default: 6 points per sprint week) that controls how many effort points fit in a single sprint slot.
4. The system must label each sprint with a calendar week: Sprint 1 starts on the Monday of the calendar week following the `--as-of` date (default: current date). Sprint N starts N-1 weeks after Sprint 1's start date. The `--as-of YYYY-MM-DD` option overrides the current date (used for deterministic testing). Note: `--duration` flag is deferred to a future enhancement — sprint duration is fixed at 1 week for MVP.
5. The system must assign tickets to the earliest sprint slot where (a) all `depends-on` dependencies are fully assigned to earlier sprint slots, and (b) the sprint's remaining capacity fits the ticket.
6. The system must detect and report circular `depends-on` chains: if a cycle is found, the command must abort with a descriptive error listing the cycle members and must not produce a partial plan.
7. The system must produce a Markdown sprint plan output with one section per sprint: sprint label (e.g. "Sprint 1 — Week of 2026-06-22"), a table of tickets (number, title, effort, status), and a capacity summary line.
8. The system must include a "Backlog overflow" section for any tickets that could not fit within a configurable max sprint count (default: 8 sprints) rather than silently generating an unbounded plan.
9. The system must fail closed on unresolvable dependencies: a ticket whose `depends-on` references a ticket number that does not exist as either an open or completed ticket must be placed in the "Backlog overflow" section (not planned) with a named warning. `depends-on` token values must be validated against `^[0-9]{4}$` before graph construction; non-conforming tokens are warned and excluded.
10. The system must be invocable as `/sprint` with no arguments to produce a default plan.

## Non-Functional Requirements

1. The command must complete within 5 seconds for a backlog of up to 100 open tickets on a standard developer machine.
2. The command is read-only: it must never write, modify, or delete any file.
3. Output must be valid Markdown renderable in any terminal or GitHub preview.

## Tech Stack

- `skills/sprint/compute.py`: Python 3.8+ stdlib only (`json`, `datetime`, `sys`, `argparse`). Invoked as subprocess by the skill; owns all deterministic logic (topological sort, bin-packing, date labeling). No new install dependencies.

## Test Strategy

| Type        | Rationale                                                                                           |
|-------------|-----------------------------------------------------------------------------------------------------|
| Unit        | `compute.py` unit tests via pytest: effort-mapping, Kahn's sort, bin-packing, cycle detection, date labeling with `--as-of` for determinism |
| Integration | Fixture `.tickets/` directory with varied ticket states; assert sprint plan Markdown output and no file modifications |

## Acceptance Criteria

- `/sprint` with a fixture of 5 open tickets (mixed effort, one dependency chain) produces a plan with correct sprint assignments.
- A ticket whose dependency is in sprint 1 appears no earlier than sprint 2.
- `--sprint-capacity 4` changes slot assignments relative to default capacity 6.
- A circular dependency (`A depends-on B`, `B depends-on A`) aborts with a descriptive cycle error.
- A ticket referencing a non-existent open or completed dependency is placed in "Backlog overflow" with a named warning; other tickets are still planned.
- A ticket missing the `effort` field is treated as `medium=2` with a "(missing effort, defaulted to medium)" warning visible in output.
- Overflow tickets (backlog beyond max sprints) appear in the "Backlog overflow" section.
- Command produces no file writes (verified by asserting no `.tickets/` modification).

## Open Questions

- Ticket 0013 (dependency DAG) defines `depends-on` in `status.md` but is not yet delivered. This ticket assumes that format is stabilized. If 0013 changes the field name, this ticket must be updated. No blocking dependency on 0013 being done first — `/sprint` can co-evolve.
- Should `/sprint` also accept a `--tickets` filter (e.g. only plan tickets with a given label or status prefix)? Not required for MVP; flag as a future enhancement.
