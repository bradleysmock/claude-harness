# Solution

**Ticket**: 0026
**Title**: Test Flakiness Detector

## Approach

Add a `/flaky` command backed by a new `flaky_detect.py` module that invokes the tests gate N times,
aggregates per-test pass/fail results using pytest `-v` output, and writes two artifacts:
`.harness/flaky-report.json` (machine-parseable IPC) and `.harness/flaky-report.md` (human-readable view).
The gate command (`/gate`) loads the JSON report before writing `gate-findings.md` and annotates matching
failures in-memory before the single final write (no TOCTOU). Path containment is enforced before any
subprocess call; the annotation step fails closed when the report is absent or unparseable.

## Components

| Component | Responsibility | Key Interface |
|---|---|---|
| `commands/flaky.md` | `/flaky` command spec — argument parsing, orchestration steps | Slash command |
| `flaky_detect.py` | Run detection: invokes pytest N times, parses per-test results, returns `FlakyReport` | `run_detection(directory: Path, runs: int, threshold: float, project_root: Path) -> FlakyReport` |
| `FlakyReport` dataclass | Typed result: `tests: list[FlakyTest]`; `FlakyTest`: `name: str, passes: int, runs: int` | Imported by gate annotation step |
| `.harness/flaky-report.json` | Machine-parseable IPC artifact between `/flaky` and `/gate` annotation | Written by `/flaky`; read by `/gate` |
| `.harness/flaky-report.md` | Human-readable ranked report; operator-facing | Written by `/flaky` alongside JSON |
| `/gate` (modified) | Load JSON flaky report before writing findings; annotate in-memory; single final write | Reads `.harness/flaky-report.json` |

## Tech Choices

| Choice | Rationale |
|---|---|
| JSON for IPC (`flaky-report.json`) | Explicit typed contract; avoids Hyrum's Law fragility of Markdown regex; schema validated on load |
| Markdown generated separately | Human-readable view decoupled from machine-parseable contract |
| pytest `--tb=no -v` for per-test parsing | Machine-parseable PASSED/FAILED per test name without extra deps |
| Sorted by fail rate descending | Unambiguous ranking criterion; consistent across different `--runs` values |
| Annotation applied in-memory before write | Single write of gate-findings.md eliminates TOCTOU window |
| Path containment check before subprocess | Fail closed on any `directory` input escaping project root |

## Security Design

- `directory` parameter resolved via `Path(directory).resolve()`, verified `relative_to(project_root)`
  before any subprocess call. Raise `ValueError` and abort if containment check fails.
- Annotation step: if `.harness/flaky-report.json` is absent, unreadable, or fails JSON schema validation,
  all gate failures remain hard blockers (fail-closed default). Error logged; no silent downgrade.

## Test Plan

| Requirement | Test Type | Scenario(s) |
|---|---|---|
| FR-2 | Unit | Mock subprocess: verify invoked N times; varying PASSED/FAILED per-test lines parsed correctly |
| FR-3 | Unit | All-pass test absent from report; all-fail test absent from report; mixed-outcome test present |
| FR-4 | Unit | Report sorted by fail rate descending; "3/5" format string correct |
| FR-5 | Integration | Full `/flaky` run on fixture produces `.harness/flaky-report.json` + `.harness/flaky-report.md` |
| FR-6 happy path | Integration | Gate annotation adds "known flaky (X/N)" label for matching test failure |
| FR-6 fail-closed | Integration | Missing `flaky-report.json` → all gate failures remain hard blockers |
| FR-6 fail-closed | Integration | Malformed JSON → all gate failures remain hard blockers; error logged |
| FR-7 | Unit | Pass rate 0.6 with `--threshold 0.8` → `0.6 < 0.8` → not in flaky report (treated as blocker) |
| NFR-2 | Unit | JSON output loads without error; schema fields present; deterministic across runs |
| NFR-3 | Integration | State of `.harness/` is identical before run N and before run N+1 within a single `/flaky` execution |

## Tradeoffs and Risks

- **Chose sequential runs**: Parallel runs mask timing-related flakiness; sequential is predictable in cost.
- **Chose test gate only**: Re-running lint/type-check N times adds cost with no benefit.
- **Integration fixture**: Counter file (`/tmp/flaky_fixture_counter`) incremented each run; fails on odd, passes on even; reset at session start — deterministic, no real randomness.
- **Stale report risk**: If `/flaky` ran on a different branch, gate annotations may be outdated. Mitigated by timestamp in flaky-report.md header; `/flaky` should be re-run when test suite changes.
- **pytest parser brittleness**: Pinned minimum pytest version in `pyproject.toml`; parser covered by unit tests.

## Implementation Order

1. Define `FlakyReport` / `FlakyTest` dataclasses and `run_detection` signature in `flaky_detect.py`.
2. Implement pytest `-v` output parser and pass/fail aggregation in `flaky_detect.py`.
3. Add unit tests in `tests/test_flaky_detect.py` (mock subprocess; covers FR-2, FR-3, FR-4, FR-7, NFR-2).
4. Implement JSON + Markdown serialization in `flaky_detect.py`; add path containment guard.
5. Add `commands/flaky.md` command spec.
6. Modify `/gate` annotation step: load JSON, annotate in-memory, single write; fail-closed guard.
7. Add integration tests covering FR-5, FR-6 (happy + fail-closed paths), NFR-3 using counter fixture.
