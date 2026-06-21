# Solution

**Ticket**: 0010
**Title**: Ticket export (JSON/CSV)

## Approach

Implement `/export` as a new markdown command file in `commands/export.md` following the same pattern as `/ticket-status` and `/cancel`. The command reads ticket directories from `.tickets/` root and `.tickets/completed/`, parses `status.md`, `problem.md`, and `solution.md` for each ticket, optionally queries `git log` for commits on the ticket branch, and writes structured JSON or CSV. All logic is expressed as bash snippets + inline Python; no compiled binary or new Python module is added.

## Output Schema

JSON field names and CSV column order are fixed — external consumers depend on this contract.

| JSON field | CSV column | Type | Source |
|------------|------------|------|--------|
| `ticket` | `ticket` | string | `status.md` → `ticket:` |
| `title` | `title` | string | `status.md` → `title:` |
| `status` | `status` | string | `status.md` → `status:` |
| `updated` | `updated` | `YYYY-MM-DD` | `status.md` → `updated:` |
| `branch` | `branch` | string | `status.md` → `branch:` |
| `problem_summary` | `problem_summary` | string\|null | First paragraph after `## Problem` in `problem.md`; null if absent |
| `solution_summary` | `solution_summary` | string\|null | First paragraph after `## Approach` in `solution.md`; null if `solution.md` absent OR heading missing |
| `commits` | `commits` | array\|string | JSON: `[{hash, message}]`; CSV: semicolon-joined `hash message` entries; empty if branch absent |
| `commits_truncated` | `commits_truncated` | bool\|string | `true` if git log returned exactly 50 results (limit hit); else `false` |

CSV nulls are serialized as empty string. All fields are `QUOTE_ALL` in CSV output.

## Components

| Component | Responsibility | Key interfaces |
|-----------|---------------|----------------|
| `commands/export.md` | Command specification: arg parsing, ticket scanning, field extraction, output formatting | Reads `.tickets/` tree; invokes `git log` via argument list; writes to stdout or `--output` file |
| README update | Add `/export` row to Slash commands → Maintenance table | Documentation only |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Markdown command file (not Python script) | All other harness commands use this pattern; no new runtime dependency |
| Python inline snippet for all serialization and parsing | `csv`/`json` stdlib handle quoting and encoding edge cases; bash cannot quote CSV fields reliably |
| `subprocess` with `shell=False` and explicit argument list | Prevents command injection from ticket branch names or directory names |
| Directory name validated against `^\d{4}-[a-z0-9-]+$` before use | Eliminates path-traversal vectors before the name reaches Python or subprocess |
| `git log --oneline --first-parent --max-count=50` on ticket branch | Scoped commit log without merges; `commits_truncated` flag signals when limit is hit |
| Default to `done`/`cancelled` only | Matches Linear's default export behavior; avoids exporting in-flight work by accident |
| Default format: JSON | JSON is more useful for programmatic import; CSV is opt-in for spreadsheet workflows |

## Security Constraints (Hard)

These are design-level constraints, not implementation suggestions:

- Directory names are validated with `re.fullmatch(r'\d{4}-[a-z0-9-]+', name)` before any further use.
- All `subprocess` calls use `shell=False` with an explicit argument list (`['git', 'log', '--oneline', ...]`).
- The resolved `--output` path is checked with `pathlib.Path.resolve()`: if it resolves inside the `.tickets/` tree, the command exits with an error before writing any file.
- No `eval`, `exec`, or dynamic code execution anywhere in the implementation.

## Test Plan

TDD order: tests written and failing before command is implemented.

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-3 (filter) | Unit | Each of `done`, `cancelled` is included; each of `problem`, `requirements`, `solution`, `implementing`, `review-ready`, `changes-requested` is excluded from default export |
| FR-4        | Unit | `--all` includes ticket at every status value |
| FR-6 (summary) | Unit | First paragraph after `## Problem` extracted correctly; leading/trailing whitespace stripped |
| FR-6 (solution) | Unit | First paragraph after `## Approach` extracted; null when heading absent; null when `solution.md` absent |
| FR-8        | Unit | Missing `solution.md` → `solution_summary` null, no exception |
| FR-9        | Unit | CSV: field with comma, newline, and quote character is QUOTE_ALL quoted correctly |
| FR-10       | Unit | JSON output parses as list; each element has all required fields |
| Schema      | Unit | JSON field names match schema table exactly; CSV header matches schema column order exactly |
| Security    | Unit | Directory name with `../`, `;`, `$(...)` is rejected by regex guard before processing |
| NFR-3 / C-07 | Unit | `--output` path resolving inside `.tickets/` raises error; path outside proceeds |
| C-09        | Unit | `commits_truncated` is `true` when git returns exactly 50 commits; `false` otherwise |
| FR-2        | Integration | `--format csv` produces header row matching schema; `--format json` produces array |
| FR-5        | Integration | `--output report.json` writes file; no `--output` writes to stdout |
| FR-7        | Integration | Ticket under `.tickets/completed/` appears in default export |
| FR-1        | Integration | Command file exists and is parseable; end-to-end run on fixture tree succeeds |

## Tradeoffs

- **Chose markdown command over Python CLI entrypoint because**: all harness commands are markdown files; a Python CLI would require a new `bin/` entry far exceeding the feature's scope.
- **Chose `QUOTE_ALL` CSV mode because**: ticket titles and summaries frequently contain commas and newlines; minimal quoting would produce unparseable output.
- **Accepting risk of**: git log unavailable in non-git environments — mitigated by `subprocess` error catch returning empty commits list.
- **`--max-count=50` truncation is documented in output** via `commits_truncated` flag so consumers can detect incomplete data.

## Risks

- Ticket directories that don't follow `NNNN-<slug>` naming (e.g., `completed/`, `NEXT_TICKET`, `.ticket.lock`) must be filtered — strict regex guard applied before any use of the name.
- `git log` on a deleted branch fails silently — `subprocess` run with `check=False`; stderr discarded; empty list returned.
- `solution.md` with non-standard heading names silently produces null `solution_summary` — acceptable; logged as empty, not an error.

## Implementation Order

1. **Write test fixtures**: create a minimal in-memory `.tickets/` structure (or temp dir fixture) covering all status values plus missing `solution.md`, missing `## Approach`, and a ticket in `.tickets/completed/`.
2. **Write failing unit tests**: filter logic, field extraction, CSV/JSON formatting, schema contract, security guards — all tests red.
3. **Write failing integration tests**: end-to-end with fixture tree for FR-2, FR-5, FR-7, FR-1 — all tests red.
4. **Implement `commands/export.md`**: argument parsing → ticket discovery → filtering → field extraction → git commit lookup → output. Tests go green.
5. **Update README.md**: add `/export` row to Slash commands → Maintenance table.
