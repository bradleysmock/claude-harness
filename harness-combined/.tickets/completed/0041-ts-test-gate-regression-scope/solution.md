# Solution

**Ticket**: 0041
**Title**: TypeScript test gate must catch regressions in unchanged tests

## Approach

Replace changed-file scoping in the directory-mode Jest gate with a full run plus
baseline-delta comparison: run jest with --json, parse failing test IDs, subtract the
cached merge-base baseline, and fail on the remainder. Baseline is computed by running
the suite once at the merge base only when a cache miss occurs, stored under
.harness/test-baselines/ keyed by SHA.

## Components

| Component | Responsibility |
|-----------|----------------|
| gates/typescript.py _test_gate_dir | Full run, JSON parse, delta computation, mode reporting |
| gates/typescript.py _baseline | Merge-base failure set: compute, cache, invalidate |
| GateResult payload | mode field + baseline_excluded list carried into gate-findings.md |
| tests/fixtures + unit tests | Regression, baseline-exclusion, and fallback scenarios |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| jest --json output | Stable test IDs; removes fragile ● stdout parsing for pass/fail sets |
| Baseline-delta over scoping | Keeps the unrelated-failure tolerance without losing regression detection |
| Cache by merge-base SHA | Deterministic, cheap, and self-invalidating as main advances |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Integration | Broken untouched test on fixture worktree fails the gate |
| FR-2 | Unit | Delta math and cache hit/miss keyed by SHA; Integration: baseline failure excluded |
| FR-3 | Unit | git absent and unknown-base fixtures produce strict full-suite behavior |
| FR-4 | Unit | GateResult carries mode and baseline_excluded; findings renderer shows them |

## Tradeoffs

- **Chose full-suite runtime cost over scoping because**: correctness of the gate is
  the harness's core promise; the baseline cache amortizes the extra run.
- **Accepting risk of**: flaky tests polluting the baseline; they surface as
  baseline-excluded lines the lead can see, and ticket 0026 (flakiness detector)
  addresses the root cause.

## Risks

- Computing a baseline requires checking out or worktree-ing the merge base; use a
  temporary detached worktree and remove it — never touch the ticket worktree.

## Implementation Order

1. Switch _test_gate_dir to jest --json full run and structured parse.
2. Implement baseline computation + cache with fallback-to-strict.
3. Thread mode/baseline_excluded through GateResult and gate-findings.md rendering.
4. Fixtures and tests; remove pass/fail reliance on _changed_test_files.
