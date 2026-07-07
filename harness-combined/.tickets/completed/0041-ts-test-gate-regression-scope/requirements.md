# Requirements

**Ticket**: 0041
**Title**: TypeScript test gate must catch regressions in unchanged tests

## Functional Requirements

1. run_typescript_suite_on_dir must run the full Jest suite; changed-file scoping must
   no longer determine which tests can fail the gate.
2. The gate must support baseline-delta mode: compute the set of failing test IDs at
   the merge base with main once per gate run cycle, cache it keyed by merge-base SHA
   under .harness/, and fail the gate only on test failures not present in that
   baseline.
3. When the baseline cannot be computed (no git, unknown base, dirty cache), the gate
   must fall back to full-suite strictness: every failure fails the gate.
4. The GateResult must report the mode used (full or baseline-delta) and enumerate any
   baseline-excluded failures so gate-findings.md shows them as informational.

## Non-Functional Requirements

1. Baseline computation must reuse the cached result across repair-loop iterations on
   the same merge base (compute at most once per SHA).
2. No new runtime dependencies; jest JSON output plus stdlib parsing only.

## Test Strategy

| Type        | Rationale                                                    |
|-------------|---------------------------------------------------------------|
| Unit        | Baseline parse/compare logic, cache keying, fallback behavior |
| Integration | Fixture TS project: broken unchanged test fails the gate; pre-existing baseline failure does not |

## Acceptance Criteria

- On a fixture worktree where the implementation change breaks an untouched test, the
  gate returns passed=false.
- On a fixture whose merge base already has one failing test, an otherwise-green
  worktree passes with that failure listed as baseline-excluded.
- The _changed_test_files scoping helper no longer gates pass/fail.
- Python/Go/Rust directory gates are unchanged.

## Open Questions

- None.
