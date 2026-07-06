# Gate Findings — 0016-health-dashboard

## Run date: 2026-07-06

### Results

| Gate       | Passed | Notes |
|------------|--------|-------|
| lint       | ✗      | 2 pre-existing I001 (skills/usage-report/analyze.py, tests/test_ticket_commit_guard.py) — baseline, not in this diff |
| type_check | ✗      | 1 pre-existing error in tests/test_ticket_commit_guard.py [arg-type] — baseline, not in this diff |
| test       | ✓      | full suite passes; 26 new tests in tests/test_health.py + tests/test_0016_health_docs.py |
| security   | ✓      | bandit clean |

### Notes

The lint and type_check gates are **red at baseline** on `main` (pre-existing debt in
`skills/usage-report/analyze.py` and `tests/test_ticket_commit_guard.py`). Ticket 0016
adds `health.py`, its tests, and the `health` skill/command; none of those files appear
in any gate failure. Per the repo's standing bar, the change introduces **no new gate
failures**. The pre-existing debt is out of scope for this ticket.
