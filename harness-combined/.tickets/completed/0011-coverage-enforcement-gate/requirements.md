# Requirements

**Ticket**: 0011
**Title**: Coverage Enforcement Gate

## Functional Requirements

1. The system must run a coverage gate after the test gate passes in directory mode
   for Python, Node.js (TypeScript/JavaScript), and Rust project directories.
2. The system must read per-language minimum thresholds from `.tickets/_thresholds.yaml`
   (parsed via `yaml.safe_load`) using keys `min_coverage_python`, `min_coverage_js`,
   and `min_coverage_rust` (integer percentages, e.g. `80`). If a key is absent or the
   file does not exist, skip enforcement for that language. An unparseable YAML file must
   produce a `COVERAGE_CONFIG_ERROR` warning and skip enforcement — never block the build.
3. The system must invoke pytest-cov for Python, nyc or c8 for Node.js, and
   cargo-llvm-cov for Rust to measure coverage.
4. The system must compute coverage delta versus the merge-base commit on the
   `main` branch and include both the absolute percentage and the delta in its output.
5. The system must block the gate (return `passed: false`) when absolute coverage
   is below the configured floor.
6. The system must skip coverage enforcement (log a warning, return `passed: true`)
   when the coverage tool is not installed rather than failing hard.
7. The system must write a `gate-findings.json` sidecar file alongside `gate-findings.md`
   containing a machine-readable `coverage` object with fields: `passed` (bool), `pct`
   (float), `delta` (float or null), `threshold` (int or null), and `status` (string).
   The `gate-findings.md` must also include a human-readable coverage section.
8. The coverage gate must be callable as a standalone `GateResult` from
   `gates/coverage.py` (`run_coverage_gate(directory, language, standards_path, base_ref, *, timeout_s=300, _runner=subprocess.run) -> GateResult`)
   and integrated into `run_suite_on_dir` for each language after the existing test gate.
9. The system must expose the coverage gate via the `gate_run_on_dir` MCP tool so
   callers receive coverage results alongside other gate results in the full-scan
   response.
10. The `/deliver` flow must refuse to proceed if `gate-findings.json` is absent,
    unparseable, or has `coverage.passed == false`. An absent or malformed sidecar must
    be treated as a failure (fail-closed), not as "no coverage data" (fail-open).

## Non-Functional Requirements

1. The coverage gate must not increase total directory-mode gate runtime by more
   than 2× the existing test gate runtime for the same project.
2. The gate must be skip-safe: a missing tool or missing base branch ref must
   never crash the harness — only produce a `passed: true` with a warning entry
   in the findings.

## Test Strategy

| Type        | Rationale                                                     |
|-------------|---------------------------------------------------------------|
| Unit        | Parse coverage output for each tool; threshold comparison logic; delta calculation |
| Integration | Run coverage gate against a small synthetic Python/Node/Rust project in a temp dir |

## Acceptance Criteria

- `gates/coverage.py` exists and exports `run_coverage_gate(directory, language, standards_path, base_ref, *, timeout_s=300, _runner=...) -> GateResult` and `load_thresholds(standards_path) -> dict[str, int]`.
- 90% coverage with floor 80 → `GateResult.passed == True`.
- 70% coverage with floor 80 → `GateResult.passed == False`, error code `COVERAGE_BELOW_THRESHOLD`.
- Tool not installed → `GateResult.passed == True`, error code `COVERAGE_TOOL_MISSING`.
- Timeout exceeded → `GateResult.passed == True`, error code `COVERAGE_TOOL_TIMEOUT` (skip, not crash).
- `gate-findings.json` written by `gate_run_on_dir`; contains `{"coverage": {"passed": ..., "pct": ..., "delta": ..., "threshold": ..., "status": ...}}`.
- `/deliver` blocks when `gate-findings.json` absent, malformed, or `coverage.passed == false`.

## Open Questions

- None. Threshold keys absent from `_standards.md` skip enforcement; that is sufficient for projects that opt out.
