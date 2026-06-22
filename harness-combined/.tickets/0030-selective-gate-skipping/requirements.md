# Requirements

**Ticket**: 0012
**Title**: Selective Gate Skipping

## Functional Requirements

1. The system must define a per-gate file-scope heuristic as a list of glob patterns or file extensions (e.g., `*.py`, `*.ts`).
2. The `gate_run_on_dir` MCP tool must accept an optional `changed_files` parameter (list of relative paths) representing the diff set.
3. When `changed_files` is provided and non-empty, the system must skip any gate whose scope heuristic has zero overlap with the provided file paths.
4. Skipped gates must produce a `GateResult` with `passed=True`, `skipped=True`, and a `skip_reason` of `"no relevant changes"`.
5. The `/gate` command must compute changed files via `git diff --name-only HEAD` before calling `gate_run_on_dir`; if `git diff` fails (no HEAD, git unavailable), the command must pass `changed_files=None` so all gates run.
6. Gates with no declared scope heuristic must never be skipped (fail-safe default).
7. When all gates are skipped, the tool must include `"any_skipped": true` in the outer response to distinguish all-skipped from all-passed.
8. Gate-findings.md written by `/gate` must include skipped gates with status `SKIP` and reason.
9. Skipped gates must not trigger fail-fast termination; the dispatch loop must continue to the next gate.

## Non-Functional Requirements

1. Skipping must add no more than 10 ms overhead (a single `git diff` call and pattern matching).
2. The `changed_files` parameter must be optional; omitting it preserves existing behavior exactly.
3. Scope heuristics must be co-located with each gate function (not in a separate config file) to keep scope and implementation in sync.
4. The `gate_run_on_dir` tool must cap `changed_files` at 10,000 entries; lists exceeding this limit are treated as `None` (run all gates) to bound the O(n×m) match loop within the 10 ms budget.

## Test Strategy

| Type        | Rationale                                              |
|-------------|--------------------------------------------------------|
| Unit        | Scope-matching logic: verify overlap detection with various glob patterns and file lists |
| Unit        | GateResult skip shape: verify skipped result fields are set correctly |
| Integration | Full `gate_run_on_dir` call with markdown-only `changed_files` — all source gates skipped |
| Integration | Full `gate_run_on_dir` call with `.py` files — python gates run, not skipped |

## Acceptance Criteria

- Given `changed_files=["README.md", "docs/guide.md"]`, lint/typecheck/test/security gates are all skipped.
- Given `changed_files=["src/foo.py"]`, all python gates run normally.
- Given `changed_files=[]` (empty list), no gates are skipped (treat as "unknown changes").
- Given no `changed_files` argument, behavior is identical to current behavior.
- Given `git diff` returns non-zero exit, the command passes `changed_files=None` and all gates run.
- Skipped gate entries in gate-findings.md show `**Status**: SKIP` and a reason line.
- A gate with no declared heuristic is never skipped regardless of `changed_files`.
- `fail_fast=True` with a skipped gate followed by a failing gate: the failing gate result is returned and no further gates run.
- `gate_run_on_dir` all-skipped response includes `"any_skipped": true`.

## Open Questions

None.
