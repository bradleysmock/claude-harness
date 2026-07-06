# Solution

**Ticket**: 0021
**Title**: Ticket velocity report

## Approach

Add a `/velocity` slash command backed by `skills/velocity/SKILL.md`. The skill reads completed ticket artifacts from `.tickets/completed/*/`, extracts dates via defined regexes, delegates cycle-time arithmetic to a deterministic Python helper script (`skills/velocity/compute.py`) to guarantee reproducibility, then emits two Markdown tables — per-ticket detail and weekly summary — plus an overall average. The command file is the skill file (no separate thin router).

## Components

| Component | Responsibility | Key Interface |
|---|---|---|
| `commands/velocity.md` | Skill definition; scan, parse, format, edge-case logic | Slash command `/velocity` |
| `skills/velocity/compute.py` | Deterministic date arithmetic: cycle time, ISO week grouping, averages | Reads JSON from **stdin**; writes JSON to stdout |
| `tests/velocity/` | Fixture ticket directories + test suite | `pytest tests/velocity/` |

## `compute.py` Interface Contract

- **Input (stdin):** JSON array of objects: `[{"id": "XXXX", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}, ...]`. Entries with malformed or missing dates are pre-filtered by the skill before being passed; `compute.py` treats any entry with non-`YYYY-MM-DD` values as an error and skips it.
- **Output (stdout):** JSON object: `{"tickets": [{"id", "start", "end", "days", "iso_year", "iso_week"}], "weekly": [{"iso_year", "iso_week", "count", "avg_days", "min_days", "max_days"}], "overall_avg": float, "skipped": int}`.
- **Exit code 0:** success (partial results if some entries were skipped).
- **Exit code 1:** fatal input error (e.g., stdin is not valid JSON); structured error written to stderr, no traceback on stdout.
- **Invocation:** `echo "$json_payload" | python skills/velocity/compute.py` — stdin transport avoids argument-length limits and shell-expansion risks.

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Python `compute.py` for date math | Deterministic: `datetime.date.fromisoformat()` + `isocalendar()` always produce the same output for the same input; LLM inference is not used for arithmetic |
| `problem.md` `**Date**` as start (creation date proxy) | Always present for well-formed tickets; represents when ticket entered active work queue. Explicitly documented in skill output header as "creation date, not status-transition timestamp." |
| `status.md` `updated` as end (latest value) | Populated by `/deliver`; if a ticket was re-delivered, the latest `updated` date is used (measures final delivery date, not first attempt) |
| ISO 8601 week grouping via `date.isocalendar()` | Correct across year boundaries (e.g., 2021-01-01 → W53-2020); not naive modular arithmetic |
| stdin transport for `compute.py` | Avoids shell argument injection; ticket data from files must not be interpolated into a shell command string |
| Collapse command and skill into one file | No routing logic in the command layer; Ousterhout: shallow wrappers add reader-hops without information-hiding value |
| Skip-and-report on bad/invalid data | Fail-open: partial data produces a useful partial report; does not abort entirely |
| Path containment validation before file open | Discovered glob paths resolved via `Path.resolve()` and verified to remain under harness root; prevents path-traversal via malformed ticket slugs |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Integration | Fixture dir with 3 completed tickets — confirm all discovered |
| FR-2,3      | Unit        | Regex extraction of `updated` and `**Date**`; YYYY-MM-DD match; non-matching formats → None |
| FR-4        | Unit        | Determinism: `(2026-01-01, 2026-01-11)` → 10 days, always; zero-day (same-day) → 0; zero-day ticket in integration fixture (Min column = 0, no divide-by-zero) |
| FR-5        | Unit        | ISO week grouping: 5 tickets across 2 weeks; year-boundary fixture (2021-01-01 → W53-2020, 2021-01-04 → W01-2021) |
| FR-6        | Integration | Per-ticket table row count matches fixture ticket count |
| FR-7        | Integration | Overall avg matches manual sum/count from fixture |
| FR-8        | Integration | Empty `completed/` dir → "No completed tickets found." message |
| FR-9        | Unit        | Missing `**Date**` → ticket skipped; skipped count reported; malformed JSON to `compute.py` stdin → exit 1, structured error on stderr, no traceback on stdout |
| FR-10       | Unit        | Negative cycle time (end < start) → ticket skipped; "invalid date range" in skip note |
| Security    | Unit        | Path traversal: ticket slug `../../etc` → resolved path fails containment check, ticket skipped |
| FR-11       | Manual      | `/velocity` invokable in live harness session (not CI-tested) |
| FR-3 | — | xref requirements.md FR-3 |
| FR-12 | — | xref requirements.md FR-12 |
| FR-13 | — | xref requirements.md FR-13 |

## Tradeoffs

- **Chose Python `compute.py` over pure Markdown arithmetic because**: date arithmetic (ISO week, day-diff) is not idempotent when delegated to LLM inference — two runs may produce different numbers on identical inputs. A 30-line Python script eliminates this class of bug entirely with no meaningful install overhead (Python is already required by the harness).
- **Collapsed command + skill into one file because**: the alternative "thin router" file adds indirection without any information-hiding value; all logic lives in the skill.
- **Using `updated` as end date (latest value, not earliest)**: measures final delivery velocity. If a ticket required rework, the longer cycle time is the true signal. Documented in output header.

## Risks

- Tickets archived before this implementation may lack a parseable `**Date**` in `problem.md` (predate the `/problem` template). Mitigation: skip-and-report (FR-9) handles this gracefully; skipped count is visible in output.
- `compute.py` requires Python 3.7+ for `date.fromisoformat('YYYY-MM-DD')` (the exact format used here). The 3.11 extension to broader ISO 8601 forms is irrelevant since the format contract is `YYYY-MM-DD` only. Add a `sys.version_info >= (3, 7)` check in `__main__`.

## Implementation Order

1. Create fixture directory `tests/velocity/completed/` with 4 tickets spanning 2 ISO weeks plus edge cases (missing date, negative range, year-boundary).
2. Write unit tests in `tests/velocity/test_compute.py` against the fixture — all failing at this point (TDD red phase).
3. Write `skills/velocity/compute.py` — date extraction, cycle-time calculation, ISO week grouping, aggregation — until tests pass (TDD green phase).
4. Write `commands/velocity.md` — skill logic that invokes `compute.py`, parses JSON output, and formats the two tables.
5. Write integration test verifying end-to-end output against the fixture (both tables, overall avg, skip count).
6. Register the command in `README.md` commands catalog.
