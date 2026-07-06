# Requirements

**Ticket**: 0024
**Title**: Ticket export (JSON/CSV)

## Functional Requirements

1. The system must provide an `/export` command accessible from Claude Code.
2. The system must support a `--format json|csv` flag defaulting to `json` when omitted.
3. The system must export completed tickets by default (status: `done` or `cancelled`).
4. The system must include open/in-progress tickets when `--all` flag is provided.
5. The system must support `--output <file>` to write to a file; when omitted, output is written to stdout.
6. Each exported record must include: ticket number, title, status, updated date (from `status.md`), problem summary (first paragraph of `## Problem` in `problem.md`), solution summary (first paragraph of `## Approach` in `solution.md`; null/empty if `solution.md` absent or `## Approach` heading missing), and associated git commits (list of `{hash, message}` objects from the ticket branch; empty list if branch absent or deleted).
7. The command must search both `.tickets/` root and `.tickets/completed/` for ticket directories.
8. The command must handle missing optional fields gracefully (e.g., no `solution.md` for a `problem`-status ticket) — omit or null the field rather than erroring.
9. The CSV output must include a header row and properly quote fields containing commas or newlines.
10. The JSON output must be a top-level array of objects, one per ticket.

## Non-Functional Requirements

1. The command must complete in under 5 seconds for up to 500 tickets on local disk.
2. No external dependencies beyond Python standard library (`json`, `csv`, `pathlib`, `subprocess`, `datetime`).
3. The command must not write to any `.tickets/` file other than the output destination.

## Tech Stack

N/A — this is a new command within the existing harness plugin. Implemented as a markdown command file in `commands/export.md` that Claude Code interprets. Any scripting logic is inline Python via Claude, not a compiled binary.

## Test Strategy

| Type        | Rationale                                                   |
|-------------|-------------------------------------------------------------|
| Unit        | Parse logic for problem/solution summaries; CSV/JSON formatting; flag parsing |
| Integration | End-to-end: given a fixture `.tickets/` tree, verify the output records match expected values for both formats and both `--all` / default modes |

## Acceptance Criteria

- `export` with no flags produces a JSON array of completed-ticket records to stdout.
- `export --format csv --output report.csv` writes a valid CSV with header row to `report.csv`.
- `export --all` includes tickets in any status, not just `done`/`cancelled`.
- Default export includes tickets with status `done` and `cancelled`; excludes all other statuses (`problem`, `requirements`, `solution`, `implementing`, `review-ready`, `changes-requested`, `escalated`, `spec`).
- A ticket with no `solution.md` exports without error; solution fields are `null` (JSON) or empty string (CSV).
- A ticket with `solution.md` but no `## Approach` heading exports without error; solution_summary is `null`/empty.
- A ticket with no associated branch/commits exports without error; commits field is empty array (JSON) or empty (CSV).
- Output includes tickets from both `.tickets/` root and `.tickets/completed/`.
- `--output` path resolving inside `.tickets/` is rejected with an error message.

## Open Questions

None.
