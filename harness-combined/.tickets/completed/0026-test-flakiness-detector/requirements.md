# Requirements

**Ticket**: 0026
**Title**: Test Flakiness Detector

## Functional Requirements

1. The system must provide a `/flaky` command that accepts an optional `--runs N` parameter (default: 5).
2. The system must execute the project's test suite N times in sequence, capturing per-run pass/fail results
   for each individual test.
3. The system must identify tests whose outcome varies across runs (at least one pass AND at least one fail).
4. The system must produce a ranked report of flaky tests sorted by fail rate descending,
   including each test's pass rate (e.g., "3/5 passed").
5. The system must write flakiness results to `.harness/flaky-report.json` (machine-parseable) and
   `.harness/flaky-report.md` (human-readable) so the gate engine can reference them.
6. The gate engine must, when a gate run produces failures, load `.harness/flaky-report.json` and annotate
   matching failures in `gate-findings.md` as "known flaky (X/N)". The annotation must be applied in-memory
   before `gate-findings.md` is written (single atomic write). When the JSON report is absent or unparseable,
   all failures remain hard blockers (fail-closed default).
7. The system must support a `--threshold` option (default: 1.0, range 0.0–1.0). A test with pass rate below
   the threshold is treated as a blocker regardless of flakiness status (i.e., if `pass_rate < threshold`,
   the test is excluded from the flaky report).

## Non-Functional Requirements

1. Each detector run must not exceed 3× the baseline gate run time (i.e., 5 runs ≈ 5× gate time, which
   is expected and acceptable; no silent overhead beyond that).
2. The flaky report must be deterministic in format so downstream tooling can parse it reliably.
3. The command must not mutate project state between runs (each run starts from the same baseline).

## Test Strategy

| Type        | Rationale                                          |
|-------------|----------------------------------------------------|
| Unit        | Run aggregation logic, pass-rate calculation, threshold comparison, report formatting |
| Integration | Full `/flaky` invocation against a fixture project with known-flaky and known-stable tests |

## Acceptance Criteria

- `/flaky` with no arguments runs the suite 5 times and produces `.harness/flaky-report.json` and `.harness/flaky-report.md`.
- A test that fails in 2 of 5 runs appears in the report with pass rate "3/5".
- A test that fails in all 5 runs does NOT appear in the flaky report (it is a consistent failure, not flaky).
- A test that passes in all 5 runs does NOT appear in the flaky report.
- Gate-findings.md annotations include a "known flaky (X/N)" label for tests matching the flaky report.
- `--runs 10` executes the suite 10 times.
- `--threshold 0.8`: a test with pass rate 0.6 (3/5) is treated as a blocker because `0.6 < 0.8` — it is excluded from the flaky report.
- When `.harness/flaky-report.json` is absent, gate-findings.md treats all failures as hard blockers unchanged.
- When `.harness/flaky-report.json` exists but is unparseable, gate-findings.md treats all failures as hard blockers; error is logged.

## Open Questions

- Should the flaky report persist across `/flaky` invocations (accumulate history), or be overwritten each
  time? The description implies a fresh report per run; assuming overwrite unless the lead specifies otherwise.
- Does "re-run" mean re-running the entire test suite or only the failing tests from run 1? Assuming entire
  suite to capture non-deterministic passes (tests that fail on some runs but pass on the first run).
