# Requirements

**Ticket**: 0007
**Title**: Ticket List Command

## Functional Requirements

1. The system must read all `status.md` files under `.tickets/*/` (open) and `.tickets/completed/*/` (completed) and aggregate their fields: `ticket`, `status`, `title`, `effort`, and `updated` (all sourced from `status.md` field values, not filesystem metadata).
2. The system must render a formatted Markdown table with columns: Ticket #, Status, Title, Effort, Updated.
3. The system must support `--open` flag to show only tickets in the `.tickets/` directory (excluding `completed/`).
4. The system must support `--completed` flag to show only tickets in `.tickets/completed/` (status `done` or `cancelled`).
5. The system must support `--status <stage>` flag to filter by the `status` field value; `<stage>` must be validated against the allow-list `problem|requirements|solution|build|review|done|cancelled` and the command must print an error and exit 1 for any other value.
6. The system must sort results ascending by ticket number by default.
7. The system must handle a missing or blank field in `status.md` gracefully — display `—` in that cell rather than crashing.
8. The system must handle a ticket directory with a missing `status.md` file by skipping that entry without error (exit 0 for the overall command).
9. The system must source the `effort` value from the `effort` field in `status.md` if present; otherwise display `—`.
10. The system must display a summary line after the table: e.g. `8 tickets (5 open, 3 completed)`.
11. The system must print "No tickets found." when no tickets match the active filter and exit 0.
12. The system must error and exit 1 when both `--open` and `--completed` are supplied.
13. The `status.md` template in `commands/problem.md` must include an `effort:` field (values: `small|medium|large`) so future tickets populate the Effort column.

## Non-Functional Requirements

1. The command must complete in under 2 seconds on a `.tickets/` directory with up to 200 tickets.
2. Output is rendered as a Markdown table; the raw table header row must not exceed 100 characters.
3. Long titles must be truncated at a column width of 40 display characters. The truncation trigger is `len(title) > 39`: a title exceeding 39 characters is truncated to 39 characters + `…` (40 display chars total). A title of 39 characters or fewer is displayed as-is.

## Tech Stack

The command is a Claude Code slash command at `commands/ticket-list.md`. It instructs Claude to run an inline Python 3.9+ script (stdlib only: `pathlib`, `re`, `sys`, `os`) that globs, parses, filters, and renders. Python 3.9 is the minimum required version for `Path.is_relative_to()`. No new package install is required.

## Test Strategy

| Type        | Rationale                                                              |
|-------------|-------------------------------------------------------------------------|
| Integration | Run command against a fixture `.tickets/` tree; assert table content and exit code |

Unit tests are not applicable: the command is a prose prompt file; the implementation logic lives in an inline Python snippet without a callable module boundary. All tests are integration-level against the full command invocation.

## Acceptance Criteria

- Running `/ticket-list` with no flags shows all tickets (open + completed) in a sorted Markdown table; exit 0.
- Running `/ticket-list --open` shows only open tickets; completed tickets are excluded; exit 0.
- Running `/ticket-list --completed` shows only completed tickets; open tickets are excluded; exit 0.
- Running `/ticket-list --open --completed` prints an error and exits 1.
- Running `/ticket-list --status solution` shows only tickets where `status: solution`; exit 0.
- Running `/ticket-list --status invalid_stage` prints an error and exits 1.
- Running `/ticket-list --status solution --open` shows only open tickets at the solution stage; exit 0.
- A ticket with no `effort` field in `status.md` displays `—` in the Effort column; exit 0.
- A ticket with a missing `status.md` file is silently skipped; remaining tickets render normally; exit 0.
- A `status.md` that is zero bytes produces an all-`—` row (not a crash); exit 0.
- A title containing `|` renders as `\|` in the Markdown table cell (does not break table structure).
- A title containing an embedded newline has the newline replaced with a single space.
- A title exceeding 39 characters is truncated to 39 chars + `…` (40 display chars total).
- The summary line accurately counts open vs. completed tickets.
- When `.tickets/` does not exist, the command prints "No tickets found." and exits 0.
- After this ticket, running `/problem` produces a `status.md` with an `effort:` line.
