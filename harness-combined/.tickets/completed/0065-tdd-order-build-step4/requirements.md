# Requirements

**Ticket**: 0065
**Title**: TDD-order build Step 4: red test gate before implementation; write files directly instead of fenced blocks

## Functional Requirements

1. Step 4 must write a spec's test file before any implementation is generated.
2. The flow must run a deterministic red-gate check against only the newly
   written test(s), against the pre-implementation worktree.
3. The check must classify its result as `red` (genuine failure attributable to
   the new test(s)), `blocking` (all new tests pass), or `tool_error` (the
   check fails to run to a conclusion). A collection/import failure from the
   not-yet-created target must classify as `red`, never `tool_error`.
4. `blocking` must revise and rewrite the test up to `MAX_REPAIR_ATTEMPTS`
   (`.harness/config.py`) before generating implementation for that spec.
5. `tool_error` must not consume a retry attempt; it escalates immediately on
   first occurrence — a broken check will not self-correct via test revision.
6. On budget exhaustion (FR-4) or a `tool_error` (FR-5), the flow must skip
   implementation for that spec and continue Step 4's loop — mirroring Step
   4e's exhaustion precedent — surfacing at Step 6/7, not halting the build.
7. After `red` is confirmed, implementation must be generated and written
   directly to its target file; test source is likewise written directly, not
   generated into fenced `# implementation` / `# tests` blocks.
8. Step 4e (`gate_run_on_dir`, full-suite, its repair loop and
   `MAX_REPAIR_ATTEMPTS`) runs unchanged and remains the final pass/fail
   authority after implementation is written.
9. The classification in FR-3/FR-5 must be a deterministic Python component,
   not a model judgment call, per the LLM/Python boundary rule.
10. The check must support Python, TypeScript, Go, and Rust, scoped to the new
    test's node id(s) when it shares a file with pre-existing tests.

## Non-Functional Requirements

1. The check runs only the new test node(s), not the full suite, staying fast
   relative to Step 4e; batch-mode builds stay compatible, running against the
   shared batch worktree exactly as Step 4e's `gate_run_on_dir` already does.

## Test Strategy

| Type    | Rationale |
|---------|-----------|
| Unit    | Per-language runner: failing/erroring new node → `red`; all-pass → `blocking`; missing-target import error → `red`; crashed runner → `tool_error` |
| Unit    | Retry/escalate decision: `blocking` retries to budget, `tool_error` escalates on first occurrence, both skip-and-continue on exhaustion |
| Content | `build-ticket.md` documents ordering, classification, direct-write, drops fenced-block language (pattern: `tests/test_0014_build_flow.py`) |

## Acceptance Criteria

- The helper reports `red` against a test with no implementation, `blocking`
  when assertions all trivially pass, `tool_error` when the runner can't run.
- A new test sharing a file with an unrelated pre-existing failure is still
  attributed by node id, not misread from the file's overall status.
- `build-ticket.md` Step 4 instructs writing tests, gating red, writing
  implementation, then Step 4e — not fenced-block generation together.
- Step 4e's gate, repair loop, and `MAX_REPAIR_ATTEMPTS` are unchanged.

## Open Questions

None — the retry budget reuses `MAX_REPAIR_ATTEMPTS` rather than a new tunable.
