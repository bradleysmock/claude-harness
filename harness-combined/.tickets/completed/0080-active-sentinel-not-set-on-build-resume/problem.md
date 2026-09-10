# Problem Statement

**Ticket**: 0080
**Title**: Set `.tickets/.active` on the normal `/build` resume path
**Date**: 2026-09-10

## Problem

`gates/coverage.py`'s `_write_sidecar` only writes `gate-findings.json` when
`.tickets/.active` (inside the worktree being gated — `server.py` derives
`standards_path` as `<directory>/.tickets/_standards.md`, so `.active`'s
parent is `<directory>/.tickets`) names the ticket. `build-ticket.md` Step 2
only writes that sentinel inside a rare fallback branch ("only if the
worktree is somehow absent"); the normal path — resuming the worktree that
already exists from claim time, true for essentially every ticket — never
writes it. `autopilot-batch.md` already sets/clears `.active` correctly for
batch mode; this gap is single-ticket-build only.

## Impact

- The coverage gate's `gate-findings.json` sidecar silently never gets
  written for a normal `/build` run, discovered while delivering ticket
  0078: `gate_run_on_dir` ran, the coverage gate itself reported a result,
  but nothing landed on disk because `_active_ticket_dir` returned `None`.
- `/deliver`'s Step 1.6 coverage preflight is fail-closed *by design*
  ("absent sidecar is a failure, never 'no coverage data'"), but the
  sentinel that makes the sidecar exist in the first place is missing for
  the common case — so the preflight has likely been silently
  unenforceable for most deliveries, not fail-closed against a real
  measurement.

Step 1's `changes-requested` resume skips Step 2 entirely on a repair
re-run; that's a no-op for this fix, not a gap it needs to cover — the
sentinel written by that ticket's earlier Step 2 run already names this
same worktree and nothing clears it mid-repair-cycle.

## Success Criteria

- `build-ticket.md` Step 2 writes `.tickets/.active` (inside the worktree)
  on every resume, not only the fallback-recreate branch.
- The sentinel names the correct slug and lives at the path the coverage
  gate actually reads (`<worktree>/.tickets/.active`, not the main
  checkout's `.tickets/.active`).
- A normal `/build XXXX` run, with `.tickets/_standards.md` present (even
  with no coverage thresholds configured), now produces a
  `gate-findings.json` sidecar without any manual workaround.
- `deliver-ticket.md` Step 6's existing cleanup (`rm -f .tickets/.active`)
  is unaffected — it already fires post-delivery.

## Out of Scope

- `autopilot-batch.md`'s sentinel handling — already correct.
- Whether the coverage gate should run when an earlier gate (e.g.
  `type_check`) has failed — that's `_append_coverage_gate`'s own
  "runs only when every prior gate passed" design choice, not a bug.
- The ~21 unrelated pre-existing mypy errors found while delivering 0079.
