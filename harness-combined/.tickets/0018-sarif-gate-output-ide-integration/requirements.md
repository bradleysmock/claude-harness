# Requirements

**Ticket**: 0018
**Title**: SARIF gate output and IDE integration

## Functional Requirements

1. The system must emit a SARIF 2.1.0-compliant file at `.harness/results.sarif` when SARIF output is enabled.
2. SARIF output must be opt-in: enabled by `--sarif` flag on `/gate` command OR by `sarif_output: true` in `.tickets/_standards.md` (harness tickets directory only — a `_standards.md` inside the scanned project worktree has no authority to enable SARIF emission).
3. When SARIF output is not opted in, the system must behave identically to today (no `.harness/results.sarif` written).
4. Each `GateError` with a non-null `file` field must map to a SARIF `result` with `ruleId` (from `code`, omitted if `code` is `None`), `level` (mapped from `severity`), `message.text`, and a `physicalLocation` with `artifactLocation.uri` (as a POSIX-relative path from `worktree_root`, not an absolute path) and `region.startLine`.
5. `GateError` entries with a null `file` field (e.g. TOOL_ERROR) must be included as SARIF results with a `artifactLocation` omitted or using a placeholder URI.
6. The SARIF `runs[0].tool.driver.name` must identify the originating gate (e.g. "ruff", "mypy", "bandit").
7. The SARIF file must include all findings from all gates in a single `runs` array entry per gate tool.
8. The `/gate` command must accept a `--sarif` flag that, when present, triggers SARIF emission after writing `gate-findings.md`.
9. The system must write the SARIF file atomically (write to a temp path, then rename) to prevent partial reads by IDE tooling.
10. The `gate_run_on_dir` MCP tool must accept an optional `emit_sarif: bool` parameter; when `True`, it writes `.harness/results.sarif` in addition to returning the JSON result.

## Non-Functional Requirements

1. SARIF file generation must add no more than 50 ms to total gate wall-clock time for a typical 200-finding result set.
2. The SARIF file must pass `sarif-tools` or equivalent schema validation without errors.
3. The module must have zero new third-party runtime dependencies (use only stdlib `json`, `pathlib`, `datetime`). `sarif-tools` is permitted as a dev/test dependency only.

## Tech Stack

Not applicable — this extends an existing Python/MCP server.

## Test Strategy

| Type        | Rationale                                                              |
|-------------|------------------------------------------------------------------------|
| Unit        | `GateError` → SARIF result mapping, severity mapping, null-file cases |
| Unit        | Atomic write: temp-then-rename produces correct file at final path     |
| Integration | `gate_run_on_dir` with `emit_sarif=True` on a real Python project dir  |
| Integration | `/gate --sarif` end-to-end: file present at `.harness/results.sarif`   |

## Acceptance Criteria

- Running `/gate XXXX --sarif` produces `.harness/results.sarif` at project root.
- The SARIF file contains one `run` per gate tool that produced findings.
- Each finding includes `ruleId`, `level`, `message.text`, and `region.startLine` where a file:line is available.
- Running `/gate XXXX` without `--sarif` (and no `_standards.md` opt-in) produces no `.harness/results.sarif`.
- The file is valid SARIF 2.1.0 (passes schema validation or VS Code SARIF Viewer loads it without errors).
- No existing gate tests regress.

## Open Questions

- Should `results.sarif` be overwritten on each run or versioned (e.g. `results-<timestamp>.sarif`)? Assuming overwrite (latest run wins) — aligns with how `gate-findings.md` works.
- Should `emit_sarif` be exposed on `gate_run` (text mode) or only `gate_run_on_dir` (directory mode)? Assuming directory mode only — text mode is for temp-dir spec runs where there are no stable file paths to anchor locations.
