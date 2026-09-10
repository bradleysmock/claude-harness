# Requirements

**Ticket**: 0079
**Title**: Commit-lint polish type + tomli/mypy gate fix

## Functional Requirements

1. `gates/commit_lint.py`'s `DEFAULT_ALLOWED_TYPES` must include `"polish"`
   alongside the existing conventional-commit types.
2. `panel_detect.py` must resolve `tomllib`/`tomli` via an
   `if sys.version_info >= (3, 11): import tomllib else: import tomli as
   tomllib` guard — the form mypy statically narrows per target Python
   version — instead of a `try/except ModuleNotFoundError`.
3. Existing behavior at runtime must be unchanged: on Python >= 3.11,
   `tomllib` is used; below 3.11, `tomli` is used (unchanged from today).

## Non-Functional Requirements

1. No other `DEFAULT_ALLOWED_TYPES` entries are removed or reordered.

## Test Strategy

| Type       | Rationale                                                          |
|------------|-----------------------------------------------------------------------|
| Unit       | commit-lint gate accepts a `polish: ...` subject; still rejects an unrecognized type |
| Unit       | `panel_detect` module imports cleanly and exposes a working `tomllib` name at runtime |
| Regression | `mypy panel_detect.py` (no `--follow-imports=skip`) exits clean with no `tomli` package installed |

## Acceptance Criteria

- `commit_lint(branch, project_root)` reports `passed: true` for a branch
  whose only non-conforming-today commit is `polish: craft round N`.
- `mypy panel_detect.py` reports no `import-not-found` error for `tomli`.
- `gate_run_on_dir` on a directory containing only unrelated Python files
  no longer fails at `type_check` because of `panel_detect.py`.

## Open Questions

None.
