# Gate Findings — 0013-build-dry-run-mode

**Worktree**: .worktrees/0013-build-dry-run-mode
**Language detected**: python

## lint

**Status**: FAIL (pre-existing baseline only — no findings in this ticket's files)

- `skills/usage-report/analyze.py:16` [`I001`]: Import block is un-sorted or un-formatted — **pre-existing**, outside 0013 scope.
- `tests/test_ticket_commit_guard.py:2` [`I001`]: Import block is un-sorted or un-formatted — **pre-existing**, outside 0013 scope.

`dry_run.py` and `tests/test_dry_run.py` produce **no** lint findings.

## type_check

**Status**: FAIL (pre-existing baseline only — no findings in this ticket's files)

- `tests/test_ticket_commit_guard.py:9` [`arg-type`]: `module_from_spec` given `ModuleSpec | None` — **pre-existing**, outside 0013 scope.

`dry_run.py` and `tests/test_dry_run.py` produce **no** type findings.

## test

**Status**: PASS

`tests/test_dry_run.py` (all cases) green alongside the full suite.

## security

**Status**: PASS

clean

---

**Note**: The two failing gates report findings exclusively in files unrelated to ticket
0013 (`skills/usage-report/analyze.py`, `tests/test_ticket_commit_guard.py`), which are
already failing on `main`. Fixing them is out of scope for this ticket and left as
separate baseline-debt cleanup. Ticket 0013's added files gate clean.
