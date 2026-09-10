# Problem Statement

**Ticket**: 0079
**Title**: Commit-lint polish type + tomli/mypy gate fix
**Date**: 2026-09-10

## Problem

Two small, pre-existing gaps block `/deliver` for any ticket that goes
through a craft-polish round or touches the Python gate suite:

1. `build-ticket.md` Step 7b.5 mandates the commit message `polish: craft
   round N` for an accepted craft round, but `gates/commit_lint.py`'s
   `DEFAULT_ALLOWED_TYPES` never included `polish` — every such commit
   fails `/deliver`'s Step 1.5 commit-lint gate.
2. `panel_detect.py`'s `try: import tomllib / except ModuleNotFoundError:
   import tomli as tomllib` fallback is unresolvable by mypy on any
   interpreter >= 3.11 with `tomli` correctly *not* installed (per its own
   `python_version < "3.11"` marker in `requirements.txt`) — mypy statically
   analyzes both branches and errors on the unresolvable `tomli` import.
   This fails the `type_check` gate for every file in the directory,
   regardless of what the diff actually touches, which in turn blocks the
   `/deliver` Step 1.6 coverage preflight (no gate run ever completes to
   write a coverage sidecar).

## Impact

- Any ticket whose build includes an accepted craft-polish round cannot be
  delivered without a manual commit-lint override.
- No ticket's `/build` can produce a passing `gate-findings.json` /
  coverage sidecar in this environment, since `gate_run_on_dir`'s
  `type_check` gate fails before completing, on a file most tickets never
  touch — silently blocking `/deliver`'s coverage preflight for everyone.

## Success Criteria

- `gates/commit_lint.py`'s default allowed types include `polish`.
- `panel_detect.py`'s tomli/tomllib import resolves cleanly under mypy with
  no `tomli` package installed, on Python >= 3.11.
- A full `gate_run_on_dir` python-suite run completes past `type_check`
  (still subject to whatever other gates find, on their own merits).

## Out of Scope

- Any other gate's behavior.
- Ticket 0078's own delivery — this ticket only removes the blockers; 0078
  is rebased and delivered separately once this lands.
