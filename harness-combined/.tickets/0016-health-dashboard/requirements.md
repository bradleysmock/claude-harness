# Requirements

**Ticket**: 0016
**Title**: Build health dashboard

## Functional Requirements

1. The system must implement a `/health` command that reads gate-findings.md files from all active and completed tickets.
2. The system must compute gate pass rate per gate type (lint, type_check, test, security, etc.) across the last 10 builds that have a gate-findings.md.
3. The system must compute average repair cycles per gate type defined as: for each `(spec_id, gate)` pair where a record with `outcome='passed'` exists, take `MAX(attempt)` as the cycle count; then average across all such pairs per gate. SQL: `SELECT gate, AVG(max_attempt) FROM (SELECT spec_id, gate, MAX(attempt) AS max_attempt FROM failure_records WHERE outcome='passed' GROUP BY spec_id, gate) GROUP BY gate`.
4. The system must query memory.db to identify the top 5 recurring failure modes — defined as the most frequently occurring error codes (patterns matching Bxxx, Exxx, TSxxxx) extracted from `errors_text` across all `failure_records` rows where `outcome != 'passed'`.
5. The system must identify which tickets had the most total gate failures (sum of failing gates across all their gate-findings.md runs).
6. The system must display a trend indicator per gate type: improving if pass-rate delta (last-5 minus prior-5) > 0.10; declining if delta < -0.10; stable otherwise (including when delta is exactly 0).
7. The system must format output for CLI readability: tables where appropriate, clear section headers, no external dependencies. The pass-rate table must include an "N of M builds analyzed" annotation where N is successfully parsed files and M is the requested window (10).
8. The system must complete execution in under 10 seconds on a repo with up to 50 tickets and a memory.db with up to 10,000 rows. Gate-findings files must be mtime-sorted and only the top-10 read (no load-all-then-slice).
9. The system must handle missing or malformed gate-findings.md gracefully (skip file, emit a warning line to stderr, continue). The "N of M builds analyzed" count must reflect the actual number of successfully parsed files.
10. The system must handle an absent or empty memory.db gracefully (omit the repair-cycle and recurring-failure sections with a note).
11. The system must validate `project_root` before any filesystem or database access: resolve to absolute path, verify it is an existing directory; raise `ValueError` if not. No path traversal outside the resolved root.

## Non-Functional Requirements

1. No writes to any file or database — the command is strictly read-only.
2. No new runtime dependencies outside the Python standard library and existing project dependencies.
3. Output must go to stdout; errors/warnings to stderr.

## Tech Stack

Not a new application — extends the existing harness plugin. Python, reads gate-findings.md (Markdown) and memory.db (SQLite via the existing `memory.py` module).

## Test Strategy

| Type        | Rationale                                          |
|-------------|----------------------------------------------------|
| Unit        | Gate pass-rate computation, trend calculation, repair-cycle aggregation, top-failure-mode extraction — each with fixture data |
| Integration | Full command execution against a synthesized .tickets/ tree and memory.db fixture; verify all output sections present and trend indicators correct |

## Acceptance Criteria

- `/health` runs without error on the real harness-combined repo.
- Gate pass-rate table is printed with at least lint / type_check / test columns when those gates exist.
- Pass-rate table shows "N of M builds analyzed" annotation.
- Trend indicator column present for each gate row (improving / declining / stable).
- Top-5 failure modes section lists error codes (e.g., B102, E501) when memory.db has failure records; section is omitted (with note) when absent.
- Average repair cycles section present when memory.db has data; computed as AVG(MAX(attempt)) per spec.
- Tickets-with-most-failures list present.
- All unit and integration tests pass, including: boundary trend test, error-code clustering, repair-cycle aggregation, and `ValueError` on invalid project_root.
- Command exits 0 on success; exits non-zero if the .tickets/ directory cannot be read.

## Open Questions

- None — required data sources (gate-findings.md format, memory.db schema) are confirmed from existing code.
