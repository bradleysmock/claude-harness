# Solution

**Ticket**: 0011
**Title**: Coverage Enforcement Gate

## Approach

Add `gates/coverage.py` as a new, language-agnostic coverage gate module that wraps
pytest-cov, nyc/c8, and cargo-llvm-cov. It is inserted after the test gate in
`run_suite_on_dir` for each language and exposed through the existing `gate_run_on_dir`
MCP tool. Thresholds are read from a dedicated `.tickets/_thresholds.yaml` file (parsed
via `yaml.safe_load`) inside `gates/coverage.py` itself — this keeps threshold discovery
co-located with the module that enforces them. `gate_run_on_dir` passes `standards_path`
to the coverage gate rather than parsing thresholds itself. Coverage results are written
to a machine-readable `gate-findings.json` sidecar alongside `gate-findings.md`; the
`/deliver` preflight reads the sidecar with a strict parser and treats missing or
unparseable as `passed: false` (fail-closed).

## Components

| Component | Responsibility | Key Interface |
|-----------|---------------|---------------|
| `gates/coverage.py` | Invoke coverage tool (argument-list only, never shell string), parse output, compare vs threshold, return `GateResult`. Validates `directory` with `Path.resolve()` before any subprocess call. Accepts optional `_runner` param (default `subprocess.run`) for test injection. | `run_coverage_gate(directory, language, standards_path, base_ref, *, timeout_s=300, _runner=subprocess.run) -> GateResult` |
| `gates/coverage.py` (internal) | Load thresholds from `.tickets/_thresholds.yaml` via `yaml.safe_load`; returns `dict[str, int]`. Absent file → empty dict (skip all). Unparseable YAML → `COVERAGE_CONFIG_ERROR` warning, skip. | `load_thresholds(standards_path) -> dict[str, int]` |
| `gates/__init__.py` | Route coverage gate into `run_suite_on_dir` after test gate, passing `standards_path` | extend `run_suite_on_dir` |
| `server.py` | Pass `standards_path` to `run_coverage_gate`; no threshold parsing in server | extend `gate_run_on_dir` |
| `gate-findings.json` (new sidecar) | Machine-readable coverage result written atomically alongside `gate-findings.md` by the coverage gate. Schema: `{"coverage": {"passed": bool, "pct": float, "delta": float \| null, "threshold": int \| null, "status": str}}` | Written by `gates/coverage.py`, read by `/deliver` preflight |
| `context/flows/deliver-ticket.md` | Preflight: read `gate-findings.json`; if absent, malformed, or `coverage.passed == false` → block with explicit message (fail-closed) | add to Step 1 validation |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| pytest-cov `--cov-report=term-missing` | Machine-parseable summary line; already a common pytest plugin |
| nyc (Node) with `--reporter=text-summary` | Widely installed; c8 is the modern alternative — detect whichever is present |
| cargo-llvm-cov `--text` | Standard coverage tool for Rust with stable text output |
| `shutil.which` for tool detection | Zero-dependency skip-safe guard already used in `_audit_gate` |
| Git merge-base for delta | Consistent with `_changed_test_files` approach in typescript.py |
| `.tickets/_thresholds.yaml` + `yaml.safe_load` | Strict machine-readable format; avoids regex on unstructured prose; `yaml` already in the stdlib-adjacent ecosystem. Absent or invalid file treated as skip, never as a configuration error that blocks |
| `gate-findings.json` sidecar | Enables fail-closed `/deliver` preflight without prose parsing; written atomically via `Path.write_text(json.dumps(...))` |
| Argument-list subprocess invocation | Required by CLAUDE.md; directory is always a list element, never interpolated into a string |
| `timeout_s=300` default for coverage runs | Consistent with existing `timeout=180` for test gates; configurable upward for large projects |
| Optional `_runner` parameter in `run_coverage_gate` | Explicit seam for unit testing without monkeypatching `subprocess` at module level |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Integration | Run coverage gate on synthetic Python/Node project in temp dir |
| FR-2        | Unit        | Parse `.tickets/_thresholds.yaml`: key present, key absent, file absent, invalid YAML |
| FR-3        | Unit        | Via `_runner` param: verify correct argument list per language; `shell=False`; directory as list element, never string-interpolated |
| FR-4        | Unit        | Delta = current − base: positive, negative, zero; base coverage run fails → delta=0 + `BASE_COVERAGE_RUN_FAILED` warning; shallow clone / missing merge-base ref → delta=0 + warning |
| FR-5        | Unit        | 70% < floor 80 → passed: False + COVERAGE_BELOW_THRESHOLD; 90% ≥ floor 80 → passed: True |
| FR-5b       | Unit        | No test files / coverage tool exits non-zero with empty output → `COVERAGE_PARSE_ERROR`, gate skips (not crash) |
| FR-6        | Unit        | `shutil.which` returns None → passed: True, error code COVERAGE_TOOL_MISSING; `gate-findings.json` section has `status: skipped` |
| FR-7        | Integration | `gate_run_on_dir` response includes coverage section in findings; tool-missing path writes `status: skipped` section |
| FR-8        | Unit        | `run_coverage_gate` and `load_thresholds` exported from `gates/coverage.py` |
| FR-9        | Integration | `gate_run_on_dir` MCP tool returns coverage in full-scan results |
| FR-10       | Unit        | `/deliver` preflight: `gate-findings.json` absent → block; `coverage.passed: false` → block; `coverage.passed: true` → allow; malformed JSON → block |
| FR-10b      | Unit        | `timeout_s` exceeded → subprocess raises `TimeoutExpired` → COVERAGE_TOOL_TIMEOUT warning, gate skips, not crash |

## Tradeoffs

- **Chose directory mode only over text mode**: Coverage tools require a real project
  structure; they cannot be sandboxed in the same temp-dir approach as text mode.
  Text-mode specs are single-function; coverage is not meaningful there.
- **Chose skip-on-missing over hard-fail**: Aligns with `_audit_gate` precedent and NFR-2.
  Teams without coverage tooling installed must not be blocked.
- **Chose project-level floor only**: Per-file granularity adds significant complexity
  with marginal value at this stage. Can be added later.
- **Chose `_thresholds.yaml` over parsing `_standards.md`**: Strict machine-readable
  format avoids the fail-open regex hazard on unstructured prose. Cost: a new file that
  operators must learn; benefit: correctness and security.
- **Chose `gate-findings.json` sidecar over prose parsing in `/deliver`**: Fail-closed
  contract for the preflight. Cost: an additional file written per gate run; benefit:
  unambiguous machine-readable verdict that cannot be fooled by formatting changes.
- **Accepting risk of**: coverage output format changes between tool versions breaking
  parsing. Mitigated by narrow regex, `COVERAGE_PARSE_ERROR` fallback with explicit error
  code and version note, and skip-safe behavior on parse failure.

## Risks

- nyc vs c8 detection: both are common Node coverage tools. Mitigated by checking for
  `nyc` first (older/more common), then `c8`; log which was selected.
- cargo-llvm-cov is not installed by default on Rust projects. Mitigated by skip-on-missing.
- Base branch ref may not exist in shallow clones (CI). Mitigated by treating missing ref
  as delta = 0 (no penalty) with `BASE_COVERAGE_RUN_FAILED` warning.
- Base coverage run could fail even when ref exists (project broken on base, no tests).
  Mitigated identically: delta = 0 + warning, no crash.
- Hung coverage subprocess. Mitigated by `timeout_s=300` default; `TimeoutExpired` →
  `COVERAGE_TOOL_TIMEOUT` skip (not crash), consistent with NFR-2.

## Implementation Order

1. `gates/coverage.py` — core module: `load_thresholds`, coverage tool invocation
   (argument-list, `shell=False`, `timeout_s`, `_runner` seam), output parsing per language,
   delta computation, `GateResult` construction, `gate-findings.json` write.
2. Unit tests (`tests/test_coverage_gate.py`) — all FR-2 through FR-6, FR-8, FR-10b scenarios
   using `_runner` injection (no subprocess monkeypatching).
3. Extend `gates/__init__.py` `run_suite_on_dir` to append coverage gate after test gate.
4. Extend `server.py` `gate_run_on_dir` to pass `standards_path` to the coverage gate
   AND integration tests verifying full `gate_run_on_dir` response (FR-7, FR-9) — treat
   Steps 4 and 5 as a single atomic deliverable.
5. Update `context/flows/deliver-ticket.md` Step 1 to read `gate-findings.json` sidecar
   (fail-closed) and block on missing/malformed/failed coverage gate.
