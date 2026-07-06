# Problem Statement

**Ticket**: 0011
**Title**: Coverage Enforcement Gate
**Date**: 2026-06-21

## Problem

The harness currently runs tests but does not enforce a minimum coverage threshold.
A passing test gate says nothing about how much of the codebase is exercised, allowing
low-coverage code to ship undetected. There is no per-language mechanism to measure
coverage delta against the base branch, so regressions go unnoticed until production.

## Impact

- Harness operators cannot trust that a green gate means adequately-tested code.
- Teams shipping via `/deliver` may silently regress test coverage over time.
- Without absolute and delta reporting in `gate-findings.md`, reviewers have no
  coverage signal at Checkpoint 1 or during diff review.

## Success Criteria

- Coverage gate runs after the test gate and blocks `/deliver` when absolute coverage
  falls below the configured floor.
- Supports pytest-cov (Python), nyc/c8 (Node.js), and cargo-llvm-cov (Rust).
- Reports absolute coverage percentage and delta vs. base branch in `gate-findings.md`.
- Thresholds are configurable per language in `_standards.md`
  (e.g., `min_coverage_python: 80`).
- Gate is skipped (with a logged warning) when the coverage tool is not installed
  rather than failing the build hard.
- Existing gate suites continue to pass with no regressions.

## Out of Scope

- Coverage enforcement for languages beyond Python, Node.js, and Rust.
- HTML or XML coverage report generation (text summary only).
- Integration with external coverage services (Codecov, CodeClimate).
- Per-file or per-module threshold granularity (project-level floor only).
