# Spec Coverage Map

**Ticket**: 0083-clear-type-check-debt-for-coverage-gate
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | `hooks/pre_write_guard.py` and `hooks/pre_ticket_diff.py` must resolve | 0083-clear-type-check-debt-for-coverage-gate-mypy-config |
| AC-4 | AC | `hooks/pre_write_guard.py` and `hooks/pre_ticket_diff.py` are otherwise | 0083-clear-type-check-debt-for-coverage-gate-mypy-config |
| FR-2 | FR | `gates/coverage.py`'s `yaml` import must resolve under mypy via an | — |
| FR-3 | FR | `tests/test_sarif.py`'s `from sarif import loader` (the third-party | — |
| FR-4 | FR | `tests/test_0067_incremental_scope.py` and `tests/test_0062_finding_key.py` | — |
| FR-5 | FR | `tests/test_regression_baseline_multilang.py`'s `load_baseline(..., | — |
| FR-6 | FR | `tests/test_0078_autopilot_watch_cli.py`'s `outcome = ...["last_dispatch_outcome"]` | — |
| FR-7 | FR | `tests/test_0031_pr_comments.py` must narrow `fetch_existing_hashes`'s | — |
| FR-8 | FR | `tests/test_0056_ticket_lock.py`'s `importlib.util.spec_from_file_location` | — |
| FR-9 | FR | `tests/test_0036_parallel_gate.py`'s `fns = {g: (lambda d, g=g: ...) for | — |
| AC-1 | AC | `mypy .` exits 0 with zero errors. | — |
| AC-2 | AC | The full test suite passes with no behavior change (same pass/fail set | — |
| AC-3 | AC | Exactly one `pyproject.toml` mypy override exists for the `sarif` | — |

## Uncovered

- FR-2 (FR): `gates/coverage.py`'s `yaml` import must resolve under mypy via an
- FR-3 (FR): `tests/test_sarif.py`'s `from sarif import loader` (the third-party
- FR-4 (FR): `tests/test_0067_incremental_scope.py` and `tests/test_0062_finding_key.py`
- FR-5 (FR): `tests/test_regression_baseline_multilang.py`'s `load_baseline(...,
- FR-6 (FR): `tests/test_0078_autopilot_watch_cli.py`'s `outcome = ...["last_dispatch_outcome"]`
- FR-7 (FR): `tests/test_0031_pr_comments.py` must narrow `fetch_existing_hashes`'s
- FR-8 (FR): `tests/test_0056_ticket_lock.py`'s `importlib.util.spec_from_file_location`
- FR-9 (FR): `tests/test_0036_parallel_gate.py`'s `fns = {g: (lambda d, g=g: ...) for
- AC-1 (AC): `mypy .` exits 0 with zero errors.
- AC-2 (AC): The full test suite passes with no behavior change (same pass/fail set
- AC-3 (AC): Exactly one `pyproject.toml` mypy override exists for the `sarif`
