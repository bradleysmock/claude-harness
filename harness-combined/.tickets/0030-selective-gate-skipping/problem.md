# Problem Statement

**Ticket**: 0012
**Title**: Selective Gate Skipping
**Date**: 2026-06-21

## Problem

The `/gate` command currently runs all configured gates unconditionally, regardless of which files changed.
For documentation-only or config-only changes, this causes test gates, lint gates, and type-check gates
to execute even when no source files they cover have been modified. This wastes time and slows feedback
loops for the harness operator.

## Impact

- Harness operators pay unnecessary gate execution time on every documentation or config change.
- A markdown-only PR may wait minutes for test/lint/typecheck gates that have no bearing on the change.
- Reduces adoption of the gate command for small, low-risk changes.

## Success Criteria

- Each gate type declares a file-scope heuristic (glob patterns or extensions).
- The `/gate` command computes changed files via `git diff` before running any gate.
- Gates whose scope has zero overlap with the changed file set are skipped automatically.
- Skipped gates emit a clear `skipped (no relevant changes)` message with the gate name.
- Gates with no declared scope heuristic are never skipped (fail-safe default).
- All existing gates continue to run correctly when relevant files are changed.
- A documentation-only change skips lint, typecheck, and test gates.

## Out of Scope

- Dynamic or user-configurable scope overrides at invocation time (e.g., `--force-all`).
- Changing how gate results are stored or reported beyond the skip message.
- Scope heuristics for gates not yet implemented in the harness.
