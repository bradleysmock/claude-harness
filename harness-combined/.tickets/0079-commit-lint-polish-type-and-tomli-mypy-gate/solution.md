# Solution

**Ticket**: 0079
**Title**: Commit-lint polish type + tomli/mypy gate fix

## Approach

Two independent one-line-shape fixes. `DEFAULT_ALLOWED_TYPES` gains
`"polish"` so the harness's own mandated craft-polish commit convention
passes the gate that's supposed to validate exactly that convention.
`panel_detect.py`'s tomli/tomllib fallback moves from a runtime
`try/except` to a `sys.version_info` guard — the one form mypy statically
narrows per configured Python version, so it never tries to resolve the
unreachable branch's import.

## Components

| Component | Responsibility |
|---|---|
| `gates/commit_lint.py` | Add `"polish"` to `DEFAULT_ALLOWED_TYPES` |
| `panel_detect.py` | Replace the `try/except` tomli import with a `sys.version_info` guard |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `sys.version_info` guard over `try/except ModuleNotFoundError` | mypy has special-cased narrowing for `sys.version_info` comparisons against the configured target version — it skips checking the unreachable branch entirely, closing the gap without installing `tomli` |
| Add to the tuple, don't replace it | Every other allowed type stays exactly as before — purely additive |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1        | Unit      | commit subject `polish: craft round 1` passes; `bogus: x` still fails |
| FR-2/FR-3   | Unit      | `panel_detect.tomllib` is a working module object at import time |
| FR-2        | Regression| `mypy panel_detect.py` (no import-skip) is clean |

## Tradeoffs

- **Chose the version-guard idiom over installing `tomli` unconditionally
  because**: `tomli` is deliberately excluded on Python >= 3.11 per
  `requirements.txt`'s own marker — installing it anyway would mask the
  actual mypy limitation rather than fix it.

## Risks

- None beyond the two files touched — both changes are additive/isolated.

## Implementation Order

1. Unit tests: commit-lint accepts `polish:`, panel_detect import shape — red first.
2. `gates/commit_lint.py`: add `"polish"`.
3. `panel_detect.py`: version-guard the import.
4. Confirm `mypy panel_detect.py` and the full test suite are clean.
