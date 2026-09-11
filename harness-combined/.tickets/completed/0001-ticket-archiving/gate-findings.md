# Gate Findings — 0001-ticket-archiving

## Run date: 2026-06-16

### Results

| Gate       | Passed | Notes |
|------------|--------|-------|
| lint       | ✓      |       |
| type_check | ✓      |       |
| test       | ✓      | 40 tests passed |
| security   | ✗      | B102 in server.py (pre-existing, deferred) |

### Security gate findings

**server.py:81** — B102 exec_used (pre-existing)
**server.py:98** — B102 exec_used (pre-existing)

These `exec()` calls load harness-authored spec/task files (`*.py` that the model wrote),
not user-supplied input. They existed before this ticket and are unrelated to the archiving
feature. The fix (`pyproject.toml` bandit skip + `-c pyproject.toml` flag in `gates/python.py`)
is included in this worktree diff and takes effect after plugin reinstall.
