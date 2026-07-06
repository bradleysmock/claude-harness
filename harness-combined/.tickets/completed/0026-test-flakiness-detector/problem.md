# Problem Statement

**Ticket**: 0026
**Title**: Test Flakiness Detector
**Date**: 2026-06-21

## Problem

Gate failures are not always deterministic: a test may pass on one run and fail on another due to timing,
environment state, or external dependencies. Currently the harness has no way to distinguish a genuine
regression from a flaky test, forcing the lead to re-run gates manually and interpret conflicting results.
This erodes trust in gate output and adds toil to every uncertain failure.

## Impact

- Harness operator (lead engineer) cannot tell whether a gate failure represents a real regression or an
  unstable test, leading to wasted investigation time and delayed delivery decisions.
- Without flakiness data, gate-findings.md treats all failures equally, blocking delivery on unreliable signal.
- Repeated manual re-runs to confirm a failure are untracked and unchanneled — the harness has no memory of
  flakiness history.

## Success Criteria

- A `/flaky` command re-runs the test suite N times (configurable, default 5) and detects tests that
  pass in some runs and fail in others.
- A ranked report of flaky tests with per-test pass/fail rates is produced.
- The gate engine can annotate known-flaky tests in gate-findings.md rather than treating them as
  hard blockers.
- The flakiness detector integrates with existing gate infrastructure (no parallel gate system).

## Out of Scope

- Automatic retry logic in the normal gate run (this ticket covers detection only).
- Root cause analysis of why a test is flaky.
- Cross-branch or historical flakiness trending (beyond a single detector run).
- Flakiness suppression (silently skipping known-flaky tests during delivery).
