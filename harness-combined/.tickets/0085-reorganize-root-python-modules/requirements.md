# Requirements

**Ticket**: 0085
**Title**: Reorganize harness-combined's flat root Python modules into a subpackage

## Functional Requirements

1. All 17 root-level modules (`server.py`, `models.py`, `memory.py`, `dag.py`, `ticket.py`, `ticket_deps.py`, `ticket_templates.py`, `audit.py`, `health.py`, `flaky_detect.py`, `learnings.py`, `panel_detect.py`, `context_rank.py`, `dry_run.py`, `sarif_output.py`, `spec_coverage.py`, `mode_branch.py`, `autopilot_watch.py`) must move into one new subpackage directory under `harness-combined/`.
2. `server.py`'s `sys.path` setup and every import statement it uses for these modules must be updated to the new location; the MCP server must start and register all 13 tools exactly as before.
3. Every hardcoded `${CLAUDE_PLUGIN_ROOT}/<module>.py` reference, anywhere in the tracked repository **except `.tickets/completed/` and this ticket's own `.tickets/0085-.../` docs** (not a fixed directory list — round 1's `commands/`/`context/flows/`/`context/helpers/`/`skills/` enumeration missed `context/harness-reference.md` and root `CLAUDE.md`, both of which contain live references), must be updated to the new path. The two exclusions are historical record, not live references — an already-delivered ticket's citation of the old path is a true fact about what it verified at the time, and this ticket's own docs narrate the move using the old paths as their subject. Live references are read as literal CLI invocation strings or cited as file paths in prose, not resolved imports, so a missed one fails silently at flow-run time or leaves stale documentation.
4. `conftest.py`'s `sys.path` insertion must be updated. `pyproject.toml`'s `mypy_path` needs no new entry — its existing `.` entry already covers `lib` as a proper package once `lib/__init__.py` exists; adding `lib` separately would create a duplicate-resolution path under `explicit_package_bases = true`.
5. Any test under `tests/` that imports a moved module directly, **or asserts on a literal old-path string** (e.g. checking that generated flow text contains `${CLAUDE_PLUGIN_ROOT}/ticket.py`), must be updated. Both categories exist today — see `tests/test_0056_ticket_lock.py` and `tests/test_0080_build_active_sentinel_doc.py` for the literal-string case.
6. Hook scripts (`hooks/*.py`) are unaffected — confirmed none of them import a root module directly — so `.claude-plugin/plugin.json`'s hook registration needs no change.

## Non-Functional Requirements

- No behavior change: gate verdicts, MCP tool responses, and CLI output must be byte-for-byte identical before and after the move.
- The migration must be mechanical and auditable (scripted `git mv` + reference rewrite), not a large hand-edited diff, given the reference count involved.

## Tech Stack

N/A — existing Python project, no new language/runtime/framework.

## Test Strategy

| Type        | Rationale                          |
|-------------|-------------------------------------|
| Unit        | Import the new package from a fresh interpreter; confirm `server.py` and `ticket.py`'s CLI entry point still run |
| Integration | Full existing pytest suite (lint/type/test) green post-move; a repo-wide grep check (not directory-scoped) asserting zero old-path references remain outside `.tickets/completed/` archives |

## Acceptance Criteria

- `find harness-combined -maxdepth 1 -name "*.py"` returns only `conftest.py`.
- Full existing gate suite (`ruff`, `mypy`, `bandit`, `pytest`) passes with no new failures.
- A repo-wide grep for each old module's `${CLAUDE_PLUGIN_ROOT}/<name>.py` pattern, across every tracked file except `.tickets/completed/` and this ticket's own docs, returns zero hits — pattern-based, not a fixed directory list, since round 1's directory enumeration missed two real files.
- `bin/harness-server` still boots the MCP server and `doctor`/`gate_run_on_dir` still respond correctly (manual smoke check).

## Open Questions

- Package name (`lib/` vs. `core/` vs. something else) — left for Solution to recommend; no blocking ambiguity.
