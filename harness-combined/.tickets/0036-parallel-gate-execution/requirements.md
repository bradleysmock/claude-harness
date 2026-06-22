# Requirements

**Ticket**: 0036
**Title**: Parallel gate execution

## Functional Requirements

1. The system must execute independent gates concurrently within a single `gate_run_on_dir` invocation (directory mode).
2. The system must enforce declared gate dependencies: a dependent gate (e.g., `test` requires `type_check`) must not start until all its prerequisites have completed and passed.
3. The system must write each gate's raw stdout+stderr to a separate log file (e.g., `.harness/gate-logs/<run-id>/<gate>.log`) upon gate completion. Log files are written before `gate-findings.md` is produced.
4. The system must write a unified `gate-findings.md` at the end of a parallel run, equivalent in content to the sequential run's output.
5. The system must respect a configurable `parallel_gate_limit` (max concurrent gates) in `_standards.md`; default is no explicit limit (all independent gates run concurrently).
6. The system must propagate gate failures correctly: if a prerequisite gate fails, dependent gates must be skipped (not silently passed) and their skip status reflected in `gate-findings.md`.
7. The system must produce measurably reduced wall-clock time versus sequential execution when two or more independent gates exist.
8. The system must remain backward-compatible: sequential behavior is preserved when `parallel_gate_limit=1` or when all gates are in a linear dependency chain.
9. Text mode (`gate_run`) is out of scope; parallel execution applies only to directory mode (`gate_run_on_dir`) invocations.

## Non-Functional Requirements

1. A gate crashing (unhandled exception) must not silently cancel sibling gates; the crash must be surfaced as a `TOOL_ERROR` finding and the run must still complete.
2. Log files must not interleave output from different gates (each gate has its own file).
3. The dependency graph must be a DAG (no cycles); cycle detection must raise at `validate_dag()` call time, not during gate execution.
4. Gate names used in log file paths must be validated as safe path components (no path separators, no `..`) before constructing the log path.

## Test Strategy

| Type        | Rationale                                               |
|-------------|----------------------------------------------------------|
| Unit        | Dependency graph construction, cycle detection, skip propagation on prerequisite failure |
| Integration | Two independent gates run concurrently; timing confirms overlap; gate-findings.md matches sequential output |

## Acceptance Criteria

- Running `gate_run_on_dir` with `fail_fast=False` on the harness project produces per-gate log files and a unified `gate-findings.md`.
- When lint and security gates are both present and independent, `GateScheduler` records overlapping `(start, end)` intervals for those gates (verified via injectable clock seam in unit tests).
- If `type_check` fails, `test` is skipped and `gate-findings.md` records the skip.
- Setting `parallel_gate_limit=1` produces identical output to the current sequential implementation.
- With `fail_fast=True`, a failing gate prevents submission of subsequent not-yet-started gates; already-in-flight gates still complete; all submitted gate results appear in the returned list.
- All existing `gate_run_on_dir` tests pass without modification.

## Open Questions

- None. Dependency graph structure (test depends on type_check) is assumed based on current sequential order in `run_python_suite_on_dir` and equivalent runners.
