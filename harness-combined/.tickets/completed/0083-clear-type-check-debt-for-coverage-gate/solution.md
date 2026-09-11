# Solution

**Ticket**: 0083
**Title**: Clear repo-wide type_check debt so the coverage gate can run

## Approach

Every one of the 25 errors falls into one of three shapes: (a) a
configuration gap mypy can't see past (`hooks/` not on `mypy_path`, a
missing stub package) — fixed by config/dependency changes, not code; (b)
a genuine `**dict`-unpacking or `object`-typed-value type-erasure pattern
in test helpers, where the underlying data really is more precisely typed
than what mypy can see — fixed by adding the precision back (typed
builders, `isinstance` narrowing, one well-placed `cast`); (c) two
genuinely mismatched call shapes (`module_from_spec` used before its
`None`-check, a closure trick that reads as 2-arity to mypy) — fixed by
reordering/restructuring, not suppressing. No category needs a blanket
ignore; category (a)'s `sarif` case is the one true "no stub exists"
permanent suppression, scoped to that one module.

## Components

| Component | Fix |
|---|---|
| `pyproject.toml` | `mypy_path` gains `:hooks`; new `[[tool.mypy.overrides]]` for `sarif` (`ignore_missing_imports`) |
| `requirements.txt` | Add `types-PyYAML` (dev/type-check only, mirrors the existing `sarif-tools` dev-dep comment style) |
| `tests/test_0067_incremental_scope.py`, `tests/test_0062_finding_key.py` | `_f(**overrides: object)` → typed keyword-only builder matching `Finding`'s fields |
| `tests/test_regression_baseline_multilang.py` | `**kw` dict-unpacking → direct keyword args; `compute` gains explicit annotations |
| `tests/test_0078_autopilot_watch_cli.py` | `isinstance`-narrow `outcome` before the `in` checks |
| `tests/test_0031_pr_comments.py` | `isinstance`-narrow `fetch_existing_hashes`'s result before `in`; new `_Capture.comments()` typed accessor replaces 3 raw accesses + the stale `type: ignore` |
| `tests/test_0056_ticket_lock.py` | Move the `assert _GUARD_SPEC is not None` before `module_from_spec` |
| `tests/test_0036_parallel_gate.py` | `lambda d, g=g: ...` dict comprehension → a typed factory function |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `hooks` on `mypy_path`, not a per-file ignore | Identical, already-precedented fix to the `tests` entry's own comment — same root cause, same solution |
| `types-PyYAML` install, not `ignore_missing_imports` | A real stub package exists; installing it is strictly better than suppressing |
| `sarif` override is the one suppression | No stub package exists for `sarif-tools`; the import itself is deliberate (AC-5 cross-verification) and already well-commented — suppressing the *symptom* here is correct because the *cause* (no stubs) is permanent and not this repo's to fix |
| Typed builders/narrowing over `# type: ignore` in test helpers | Every one of these is a real precision loss mypy is correctly catching — a builder/cast fixes the root cause once, at the definition, instead of chasing per-line ignores that drift out of sync with mypy's exact error codes (as the stale `union-attr` comment already demonstrates) |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-1/FR-2/FR-3 | Regression | `mypy .` no longer reports the `_common`, `yaml`, or `sarif` import errors |
| FR-4        | Unit      | the new `Finding` builder produces the same object for the same overrides as the old `**dict` version |
| FR-5        | Unit      | both `load_baseline` call sites behave identically with explicit kwargs |
| FR-6/FR-7   | Regression | `mypy .` no longer reports the `object`-operand errors in either file; `_Capture.comments()` returns what the raw access returned |
| FR-8        | Regression | `mypy .` no longer reports the `module_from_spec` error; the module still loads and executes identically |
| FR-9        | Unit      | the factory-produced closures still resolve to the correct per-name gate function (the exact bug `g=g` was preventing) |
| All         | Regression | full `pytest` suite unchanged pass/fail set; `mypy .` exits 0 |

## Tradeoffs

- **Fixed every real error at its source instead of suppressing because**:
  problem.md's own success criteria rule this out, and the codebase's LLM/
  Python-boundary convention treats a Python-computed verdict as
  authoritative — suppressing a real mismatch would make mypy lie about
  actual type safety, not just about this ticket's scope.
- **Accepting risk of**: none beyond ordinary test-refactor risk — every
  change is behavior-preserving by construction (typed data in, same value
  out); the full suite re-run is the actual proof.

## Risks

- `hooks` on `mypy_path` could theoretically introduce mypy's "Source file
  found twice under different module names" diagnostic for a file
  reachable via two roots at once — not the "Duplicate module named" class
  `explicit_package_bases` handles (that requires two *different* files
  claiming one name; this would be one file, two paths to it). No code
  imports `hooks.*` today and `hooks/` has no `__init__.py`, so this isn't
  expected to fire — the Implementation Order's `mypy .` re-run (step 4)
  is the actual verification, not this description.

## Implementation Order

1. Unit tests for the `Finding` builder and `load_baseline` call-site
   behavior, and for `_Capture.comments()` — red first (they fail today
   only in the sense that the functions/methods don't exist yet).
2. `pyproject.toml` + `requirements.txt` config fixes (FR-1/FR-2/FR-3).
3. Test-file fixes (FR-4 through FR-9), one file at a time, running `mypy
   <file>` after each to confirm that file's errors clear without
   introducing new ones elsewhere.
4. Full `mypy .` run — confirm zero errors.
5. Full `pytest` suite — confirm unchanged pass/fail set.
