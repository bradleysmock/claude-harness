# Requirements

**Ticket**: 0047
**Title**: Honest handling of unsupported and mis-detected stacks

## Functional Requirements

1. gate_run_on_dir with language "auto" must return a structured error naming the
   directory and any unrecognized marker files when no supported stack is detected,
   instead of defaulting to Python.
2. _detect_stacks must detect go.mod one directory level down, matching the existing
   Cargo.toml and package.json behavior.
3. All recursive file probes in _detect_stacks and stop_full_gate.detect_stacks must
   exclude vendored and generated directories: node_modules, .venv, venv, .git, dist,
   target, __pycache__.
4. stop_full_gate must write a single warning line to stderr (exit 0) when a
   review-ready worktree yields zero detected stacks, naming the worktree.
5. _detect_language's bare-Python fallback must be removed in favor of the explicit
   unsupported error path; existing single-language callers must keep their behavior
   for the four supported languages.

## Non-Functional Requirements

1. Detection must remain fast on large worktrees (bounded glob depth; no full rglob of
   vendored trees).
2. Error messages must name the remediation: pass an explicit language or add gate
   support.

## Test Strategy

| Type | Rationale                                                       |
|------|-------------------------------------------------------------------|
| Unit | Fixture directories per case: unsupported, subdir go.mod, vendored-only .py files, zero-stack hook warning |

## Acceptance Criteria

- A Java-only fixture returns an unsupported-stack error from auto mode, not Python
  tool errors.
- A fixture with api/go.mod is gated as Go.
- A JS fixture whose only .py files live in node_modules is not gated as Python.
- The Stop hook on a zero-stack review-ready fixture emits the warning and exits 0.

## Open Questions

- None.
