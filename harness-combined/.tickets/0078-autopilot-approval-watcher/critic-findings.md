## Round 1 — 2026-09-10

## Panels Active

Determined from `context/panels/triggers.md` against the in-scope files (no Bash tool available to run `panel_detect.py` directly, so triggers applied manually against the file list):

- **Core** — always active.
- **Python** — `globs: **/*.py` matches `autopilot_watch.py` and all `tests/test_0078_*.py`; `manifests: pyproject.toml` also present at root.
- **Testing** — `globs: **/tests/**` matches all four new test files.
- **Shell** — `content: ^#!.*\b(sh|bash|zsh)\b` matches `bin/autopilot-watch`'s `#!/usr/bin/env bash` shebang.
- No candidates deferred; no other manifests/deps/content triggers fired for this file set.

## Findings

**BLOCKER — Requirements coverage (FR-9) / solution.md Risks section — dispatch exit code is silently discarded, never surfaced.**
`autopilot_watch.py:212-216` (`run_tick`): `dispatch_fn(target)`'s return value — `default_dispatch`'s `result.returncode` — was called and thrown away. A `claude -p "/autopilot XXXX"` invocation that exits non-zero (build failure, permission mismatch) was indistinguishable from a clean success. Contradicted solution.md's Risks section ("mismatch is visible via `status`'s exit-code field") and the Test Plan's "status reports outcome/**exit code**." No test asserted a non-zero-exit dispatch was ever reported differently from success.

**BLOCKER — Requirements coverage (FR-9) / commands/autopilot-watch.md — "interrupted" outcome is documented but never implemented.**
Requirements.md line 40 and `commands/autopilot-watch.md` both stated that `status` reports "interrupted" when a `stop`-sent signal is caught mid-dispatch. Nothing registered a `signal.signal` handler anywhere. `test_stop_mid_dispatch_terminates_child_and_keeps_log_entry` verified the dispatch-log entry survives and `stop` returns quickly, but never asserted anything about `status.json`'s `last_dispatch_outcome`.

**BLOCKER — Requirements coverage (FR-4) — fail-closed gate skips are never logged.**
Requirements.md: "Any failure ... skips **and logs** the ticket." `is_approval_valid`/`find_dispatchable` silently dropped gate-failing tickets from the candidate list with no write anywhere distinguishing "seen and rejected by the gate" from "not yet a candidate." No logging was exercised or asserted anywhere in the suite.

**MAJOR — Core Dimension 4 (documentation contract) / FR-11 — `commands/autopilot-watch.md` never instructs the agent to run anything.**
The doc described what each subcommand *does* in prose but contained no directive analogous to other commands' explicit execution steps — no "Run `bin/autopilot-watch <subcommand> $ARGUMENTS`" anywhere. `tests/test_0078_autopilot_watch_command_doc.py` only checked for prose keywords, so this gap was untested as well as unimplemented.

**MINOR — Testing panel Dimension 22 ("test setup duplication") / Core Dimension 5 (duplication) — inconsistent fixture-sharing across the two test files.**
`tests/test_0078_autopilot_watch_cli.py` duplicated `_init_repo` verbatim from `tests/test_0078_autopilot_watch_core.py`, then separately reached into the other test module at runtime via `from tests.test_0078_autopilot_watch_core import (...)` — the only cross-test-module import in the repo, depending on pytest's import-mode/sys.path behavior rather than a shared fixture module.

**OBS — Core Dimension 6 (Parnas/information hiding) / FR-3 alignment — discovery mechanism deviates from the literal requirement, but is explained.**
Requirements.md FR-3 specifies scanning `.worktrees/*/.tickets/*/status.md` and validating directory names before use. `scan_worktree_tickets` instead reuses `ticket.list_tickets`'s ledger-driven enumeration — a stronger, differently-shaped guarantee — explicitly rationalized in the module docstring. OBS rather than MAJOR since the deviation is documented.

### Repair (commit `5dbc526`)

- **BLOCKER 1** — `run_tick` now returns `exit_code` from the dispatch call; `cli_tick`'s outcome string includes it (`"dispatched 0001 (exit 1)"`). New test: `test_run_tick_surfaces_dispatch_exit_code`, `test_cli_tick_records_exit_code_in_outcome`.
- **BLOCKER 2** — `cli_tick` now installs a SIGTERM handler that writes `last_dispatch_outcome="interrupted"` before re-raising. `test_stop_mid_dispatch_terminates_child_and_keeps_log_entry` now asserts the snapshot reads `"interrupted"` after `stop`.
- **BLOCKER 3** — `find_dispatchable` now logs every gate rejection (with reason) to `.harness/autopilot-watch/rejections.log` via `_log_rejection`. New test: `test_content_drift_after_approval_is_logged`.
- **MAJOR** — Added a `## Steps` section to `commands/autopilot-watch.md` naming the exact `bin/autopilot-watch <subcommand> . [--interval N]` invocation. New test: `test_documents_execution_directive`.
- **MINOR** — Extracted `tests/_watch_fixtures.py`; both test files now import from it instead of duplicating or cross-importing.
- **OBS** — No change; left as documented, deliberate deviation.

## Round 2 — 2026-09-10

Verification round. Read the code/tests directly rather than trusting the round-1 repair summary.

- **BLOCKER 1 (dispatch exit code discarded) — RESOLVED.** `run_tick` returns `exit_code`; `_outcome_label` folds it in. Verified by `test_run_tick_surfaces_dispatch_exit_code` and `test_cli_tick_records_exit_code_in_outcome`.
- **BLOCKER 2 ("interrupted" outcome never implemented) — RESOLVED.** `cli_tick`'s SIGTERM handler writes `"interrupted"` before re-raising; `_Interrupted` is not `OSError` so `run_tick` doesn't swallow it. `test_stop_mid_dispatch_terminates_child_and_keeps_log_entry` now asserts the post-stop snapshot.
- **BLOCKER 3 (fail-closed gate skips never logged) — RESOLVED.** `_log_rejection` appends to `.harness/autopilot-watch/rejections.log`, gitignored. Verified by `test_content_drift_after_approval_is_logged`.
- **MAJOR (no execution directive) — RESOLVED.** `commands/autopilot-watch.md`'s new `## Steps` section names the exact `bin/autopilot-watch <subcommand> . [--interval N]` invocation, matching the `bisect.md`/`solution.md` convention.
- **MINOR (fixture duplication) — RESOLVED.** `tests/_watch_fixtures.py` extracted; no cross-module `from tests.` import remains.

### New findings (MINOR — not auto-fixed per severity policy; listed for the lead)

- **MINOR — `running` field in `status.json` is written with contradictory values (`True` on a normal tick, `False` from the interrupt handler) but `cli_status` never reads it — derives liveness from the PID file instead. Dead, misleading field.** Fix shape: drop `running`/`pid` from `write_status_snapshot`'s persisted shape (keep them CLI-computed), or wire `cli_status` to actually use the persisted value and pick one source of truth.
- **MINOR — `_log_rejection` appends one line per tick for a persistently-rejected ticket, unbounded (no dedup, no rotation).** Fix shape: dedup by `(ticket, approved_commit, reason)` before appending, or log only on state transition.

No BLOCKER/MAJOR remain. Proceeding to craft polish and the delivery handoff.
