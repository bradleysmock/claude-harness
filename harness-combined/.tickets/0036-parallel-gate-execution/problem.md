# Problem Statement

**Ticket**: 0017
**Title**: Parallel gate execution
**Date**: 2026-06-21

## Problem

- `/gate` runs each phase (lint, typecheck, test, security) sequentially even when phases are independent, creating unnecessary wall-clock latency on every gate invocation.
- On codebases where tests and lint/typecheck are fully independent, the operator waits for them to complete in series — a structural inefficiency baked into the current gate runner.
- No mechanism exists to express phase dependencies (e.g., test depends on typecheck) or to control parallelism level.

## Impact

- Harness operators (lead engineers) experience inflated feedback cycles during development and CI, slowing iteration.
- Large projects with multi-second test suites and independent lint/typecheck steps incur compounding wait times with no technical justification.
- Without a dependency graph, adding parallelism naively risks launching tests against unverified type-incorrect code.

## Success Criteria

- Independent gate phases run concurrently within a single `/gate` invocation.
- Dependent phases (e.g., test requires successful typecheck) remain sequential per declared dependency graph.
- Each phase streams its output to a separate log file; a unified `gate-findings.md` is written at the end.
- Parallelism level (max concurrent phases) is configurable in `_standards.md`.
- Wall-clock time for a full gate run with independent phases is measurably reduced versus sequential baseline.
- No regression: gate output and `gate-findings.md` content are equivalent to sequential execution.

## Out of Scope

- Cross-ticket or cross-run parallelism (this feature is per-invocation only).
- Dynamic dependency inference (dependencies are declared, not auto-detected).
- Distributed execution across machines.
- Changes to gate phase definitions or gate repair loop behavior.
