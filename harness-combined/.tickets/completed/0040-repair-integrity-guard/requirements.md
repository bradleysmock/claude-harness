# Requirements

**Ticket**: 0040
**Title**: Repair-integrity guard against gate gaming

## Functional Requirements

1. A pure, unit-tested function in gates/repair_integrity.py must classify a unified
   diff and report violations: removed test functions (def test_, it(, test(, func Test,
   #[test]), added skip/xfail markers, and net-new suppression pragmas (noqa,
   type: ignore, nosec, nolint, eslint-disable variants, ts-ignore, ts-expect-error,
   as any, #[allow) across Python, TypeScript/JS, Go, and Rust.
2. build-ticket.md Steps 4e and 7a must run the integrity check on each repair round's
   diff; any violation must fail the round and re-enter repair with the instruction to
   restore the test and fix the implementation instead.
3. pre_write_guard.py must accept a suppression marker only when it carries a reason
   suffix on the same line (for example "# nosec: fixture uses literal creds"); bare
   markers must block the write with a fix hint.
4. stop_full_gate.py must count net-new suppression pragmas in the active worktree's
   diff against main and include them in its blocking report when unexplained.
5. context/critic-brief.md Step 2.5 must instruct the code-mode critic that tests
   weakened or deleted relative to solution.md's Test Plan are BLOCKER findings.

## Non-Functional Requirements

1. The classifier must be pure (no I/O) so it is unit-testable like spec_remediate.py.
2. Per-round classification must complete in under 1 second on a 5000-line diff.
3. False-positive escape hatch: reasons are free-text; the guard never judges adequacy.

## Test Strategy

| Type | Rationale                                                        |
|------|-------------------------------------------------------------------|
| Unit | Classifier: each violation class per language, plus clean diffs   |
| Unit | pre_write_guard reason-suffix acceptance and bare-marker blocking  |
| Unit | Docs greps: build-ticket wiring text, critic-brief BLOCKER wording |

## Acceptance Criteria

- A diff deleting a pytest test or adding bare "# noqa" is classified as a violation;
  the same diff with a reasoned marker and no test deletion passes.
- Writing a file with bare "# nosec" is blocked; with "# nosec: reason" it is allowed.
- build-ticket.md contains the integrity-check step in 4e and 7a.
- Existing hook and gate tests pass unchanged.

## Open Questions

- None.
