## Round 1 — 2026-09-10

**Panels active:** Core, Python, Testing.

**MINOR — the new test file exercised only the pattern helper, not `commit_lint.run()` end-to-end, though requirements.md's acceptance criterion is stated against `run()`.** Fixed: added `test_polish_commit_passes_end_to_end`, a self-contained integration test (local `_git`/`_commit` helpers, no cross-module import) asserting `run("feature", str(repo)).passed is True` for a `polish: craft round 1` commit.

**OBS — `gates/python.py` and `gates/rust.py` still use the older `try/except ModuleNotFoundError` tomli fallback (currently suppressed by `type: ignore`, not failing).** Left alone — explicitly out of this ticket's scope (problem.md), not currently broken. Noted here so a future ticket touching either file knows the `sys.version_info` guard in `panel_detect.py`/`gates/__init__.py` is the now-preferred idiom for this repo.

No BLOCKER/MAJOR findings.
