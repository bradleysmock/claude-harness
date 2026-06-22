# Solution

**Ticket**: 0016
**Title**: Build health dashboard

## Approach

Add a `/health` command backed by a new `health.py` module that reads gate-findings.md files from active and completed tickets and queries memory.db directly via sqlite3. The command aggregates gate pass rates, repair cycles, recurring failure modes, and top failing tickets, then prints a structured CLI report to stdout. No new runtime dependencies; no writes. `project_root` is validated (resolved to absolute path, must exist as a directory) before any filesystem or DB access — the module fails closed on invalid paths.

## Components

| Component | Responsibility | Key Interfaces |
|-----------|---------------|----------------|
| `commands/health.md` | Command entry point — instructs Claude to invoke the health skill | Calls `health` skill |
| `skills/health/SKILL.md` | Orchestration: discovers tickets, calls health_report(), calls format_report(), prints to stdout | Calls `health_report()` then `format_report()` |
| `health.py` | Data collection, computation, and formatting: parse gate-findings.md, query memory.db, compute metrics, render CLI output | `health_report(project_root: str) -> HealthReport`; `format_report(report: HealthReport) -> str`; `HealthReport` is a typed dataclass |
| Unit tests in `tests/test_health.py` | Tests for all computation functions with fixture data | pytest |
| Integration test | Runs full skill execution, captures stdout, asserts on section headers and column names | pytest |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Python module (`health.py`) alongside `memory.py` | Consistent with existing server.py pattern; reuses `sqlite3` already present |
| Regex-based gate-findings.md parser | No external Markdown library needed; gate-findings format is controlled and simple |
| Direct sqlite3 queries (not SQLiteFailureMemory) | `retrieve_similar` is BM25 search — not suited for aggregation; raw SQL GROUP BY is the right tool |
| Skill-based command (not MCP tool) | Aggregation is orchestration logic, not a mechanical tool; consistent with `status` skill pattern |
| Trend computed as last-5 vs previous-5 builds | Balances sensitivity and noise; robust with as few as 6 data points |
| `HealthReport` typed dataclass | Explicit contract between `health.py` computation and `format_report()` formatting; prevents key-name drift |
| `format_report()` in `health.py`, called by skill | Skill stays thin; formatting logic is testable Python, not embedded in SKILL.md prose |
| Error-code clustering for failure modes | Uses existing tokenizer regex patterns (Bxxx, Exxx, TSxxxx) from `memory.py`; clusters by code not raw text |

## Test Plan

| Requirement | Test Type   | Scenario(s)                                                                      |
|-------------|-------------|----------------------------------------------------------------------------------|
| FR-2        | Unit        | pass_rate_by_gate: 8 fixtures, mixed pass/fail; assert "N of M" denominator in output |
| FR-3        | Unit        | avg_repair_cycles: two specs for same gate, attempts 1–3 then pass; assert AVG(MAX(attempt)) not naive AVG; SQL: `SELECT gate, AVG(max_attempt) FROM (SELECT spec_id, gate, MAX(attempt) AS max_attempt FROM failure_records WHERE outcome='passed' GROUP BY spec_id, gate) GROUP BY gate` |
| FR-4        | Unit        | top_failure_modes: 20 records with known error codes (B102, E501, TS2345); verify output lists codes not raw text blobs |
| FR-5        | Unit        | top_failing_tickets: 6 tickets, verify sort order by total gate failures          |
| FR-6        | Unit        | trend_indicator: boundary case delta=0.10 exactly → stable; delta=0.11 → improving; delta=-0.11 → declining; equal pass rates → stable |
| FR-9        | Unit        | malformed gate-findings.md: no exception raised; warning to stderr; N-of-M count reflects skipped file |
| FR-10       | Unit        | absent memory.db returns None sections gracefully; output includes note           |
| C-01        | Unit        | health_report("/etc") raises ValueError before any FS access                     |
| FR-1–FR-8   | Integration | full skill execution, stdout captured; assert section headers present, column names correct, "N of M" annotation present |

## Tradeoffs

- **Chose skill over MCP tool**: The health command is read-only orchestration; MCP tools are for gate execution and memory I/O. Consistent with `status` skill precedent.
- **Chose regex over a full Markdown parser**: gate-findings.md format is internal and controlled; pulling in `mistletoe` or similar for a read-only parser is unnecessary complexity.
- **Accepting risk of**: gate-findings.md format drift breaking the parser — mitigated by graceful skip-and-warn on parse failure (FR-9), and "N of M builds analyzed" transparency in the pass-rate table header so leads can see when files were skipped.
- **Chose error-code clustering over raw text for failure modes**: extracts Bxxx/Exxx/TSxxxx codes via the existing `_tokenise()` regex patterns from `memory.py` rather than grouping by raw `errors_text`, which would never cluster similar errors.
- **Trend threshold**: delta > 0.10 = improving; delta < -0.10 = declining; within ±0.10 = stable. This is enforced in `trend_indicator()` and specified as the acceptance criterion.

## Risks

- gate-findings.md format has no formal schema; parser must be defensive. Mitigated by FR-9 (skip + warn) and unit test for malformed input. Pass-rate table shows "N of M builds analyzed" so leads see when files were skipped.
- memory.db may not exist on fresh repos or projects that have never run a build. Mitigated by FR-10 (graceful omission).
- Last-10-builds window: files are mtime-sorted first, then only the top-10 are read — avoids loading all files before slicing.
- `project_root` trust boundary: resolved to absolute path via `Path(project_root).resolve()` before any filesystem access; raises `ValueError` on invalid input (no such directory). Test case: `health_report("/etc")` raises `ValueError`.

## Implementation Order

1. Define `HealthReport` dataclass and all function signatures in `health.py` (no bodies) — establishes the contract before tests are written.
2. Write `tests/test_health.py` with all unit test cases including boundary and error-code fixtures (TDD — tests before implementation).
3. Implement `health.py` bodies: `_validate_project_root()`, `parse_gate_findings()`, `pass_rate_by_gate()`, `avg_repair_cycles()`, `top_failure_modes()`, `top_failing_tickets()`, `trend_indicator()`, `health_report()`, `format_report()`.
4. Verify all unit tests pass.
5. Write integration test: synthesize fixture .tickets/ tree + tmp memory.db; invoke `format_report(health_report(root))`; capture stdout; assert section headers, "N of M" annotation, column names.
6. Implement `skills/health/SKILL.md` — thin orchestration (call `health_report()`, call `format_report()`, print to stdout).
7. Implement `commands/health.md` — thin command entry point.
8. Run full gate suite; address any findings.
