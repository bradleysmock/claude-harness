Flaky-test detector — re-runs the project's test suite N times and reports tests whose outcome is non-deterministic (pass on some runs, fail on others). Backed by `flaky_detect.run_detection`. Writes `.harness/flaky-report.json` (machine-parseable) and `.harness/flaky-report.md` (human-readable).

## Arguments

- `--runs N` — number of times to re-run the suite. Optional; default `5`.
- `--threshold T` — minimum pass rate for a varying test to still be reported as flaky, range `0.0`–`1.0`. Optional; default `0.0` (report every detected flaky test). A test whose pass rate is below the threshold (`pass_rate < threshold`) is excluded from the flaky report and treated as a blocker.

> Note: requirements.md FR-7 names a `--threshold` default of `1.0`, but that value is inconsistent with the acceptance criteria — a `1.0` default would exclude every flaky test (all have `pass_rate < 1.0`), making the default report always empty. The functional default is therefore `0.0`. Flagged for the lead.

## What counts as flaky

A test is flaky when, across the runs, it has **at least one PASS and at least one FAIL**. Consistency at either extreme is *not* flaky:

- A test that passes in **all** runs is stable — not reported.
- A test that fails in **all** runs is a consistent failure (a real regression), not flaky — not reported.
- A test that fails in, e.g., 2 of 5 runs is flaky and appears with a pass rate of `3/5 passed`.

## Steps

1. **Resolve the directory** to run tests in (default: the project root). Resolve it with `Path.resolve()` and verify it is **contained within** the project root before anything else — a directory that escapes the project root raises `ValueError` and aborts (no subprocess is launched).
2. **Run detection**: call `flaky_detect.run_detection(directory, runs, threshold, project_root)`. It invokes pytest (`--tb=no -v`) `runs` times in sequence, parses per-test PASSED/FAILED results, and aggregates pass/fail counts per test. The suite is re-run in full each time (not only the run-1 failures) so tests that pass on the first run but fail later are still caught. Project state is not mutated between runs.
3. **Write the reports**: call `flaky_detect.write_reports(report, harness_dir)` to write `.harness/flaky-report.json` and `.harness/flaky-report.md`. The report is ranked by fail rate descending; each row shows the pass count as `X/N passed`.
4. **Print a summary line** naming how many flaky tests were found and the two artifact paths.

## Notes

- The JSON report is the contract read by the `/gate` annotation step; the Markdown report is the operator-facing view (with a generated-at timestamp in its header).
- Re-run `/flaky` when the test suite changes — the reports reflect a single detector run and do not accumulate history.
