# Solution

**Ticket**: 0085
**Title**: Reorganize harness-combined's flat root Python modules into a subpackage

## Approach

Introduce one new package directory, `lib/`, at `harness-combined/` root. Move all 17 flat modules into it with `git mv` (preserving history), add `lib/__init__.py`, then mechanically rewrite every reference to the old flat paths — imports in `server.py`, `sys.path` in `conftest.py`, and every tracked file (not a fixed directory list) containing a `${CLAUDE_PLUGIN_ROOT}/<module>.py` pattern. A small Python rewrite script (not committed — a one-off migration aid) does the reference sweep by pattern match across the whole repo, so the change is auditable, re-runnable, and can't silently exclude a directory nobody thought to enumerate — round 1 of this design missed `context/harness-reference.md` and root `CLAUDE.md` exactly that way.

## Components

| Component | Responsibility |
|---|---|
| `lib/` (new) | Home for all 17 modules; flat within the package, mirroring `gates/`'s own flat-within-package style |
| `server.py` | Updated imports (`from lib import dag`, etc.); `sys.path` insert unchanged (still inserts plugin root) since `lib` is a proper package |
| `conftest.py` | `sys.path` comment/logic updated to note `lib/` is now a package, not a flat root import target |
| `pyproject.toml` | **No change** — `mypy_path`'s existing `.` entry already resolves `lib` as a package once `lib/__init__.py` exists; adding `lib` as a second entry would create a duplicate-resolution path under `explicit_package_bases = true`, the exact ambiguity that setting exists to prevent |
Every tracked file, repo-wide, **except `.tickets/completed/` and this ticket's own `.tickets/0085-.../`** | Every `${CLAUDE_PLUGIN_ROOT}/<module>.py` → `${CLAUDE_PLUGIN_ROOT}/lib/<module>.py`, found by pattern match rather than a directory list — includes `commands/*.md`, `context/**/*.md` (including `context/harness-reference.md`), `skills/*/SKILL.md`, and root `CLAUDE.md`. The two exclusions are historical record, not live references: `.tickets/completed/*` documents what an already-delivered ticket verified *at the time* (e.g. ticket 0053 citing `ticket.py`'s old path is a true historical fact, not a stale reference to fix), and this ticket's own design docs narrate the move using the old paths as the subject under discussion — rewriting them mid-flight would garble the ticket's own record once archived. The rewrite script excludes both paths by the same rule the verification grep already uses, applied at the same step rather than only at verification |
| `tests/*.py` | Direct `import <module>` / `from <module> import X` updated to `from lib import <module>` / `from lib.<module> import X`; separately, tests asserting on a *literal old-path string* in generated flow text (e.g. `tests/test_0056_ticket_lock.py`, `tests/test_0080_build_active_sentinel_doc.py`) get their expected-string literals updated too — a distinct fix from an import update |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Single flat `lib/` package, not split by concern | Matches the existing one-directory-per-concern convention (`gates/`, `hooks/`); a deeper split is speculative and unrequested |
| Scripted, repo-wide pattern rewrite, not a directory-enumerated pass | ~90 reference sites (roughly 40 CLI/prose references plus ~49 test files with direct imports) make a manual or directory-scoped pass error-prone — round 1's directory list already missed two real files; matching by pattern across every tracked file removes that failure mode structurally |
| `from lib import X` imports, not path-hack `sys.path` tricks per module | `lib/__init__.py` makes it a real package; avoids the fragile per-file `sys.path.insert` pattern hooks currently use for `_common` |

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1 (relocate) | Unit | `find harness-combined -maxdepth 1 -name '*.py'` returns only `conftest.py` |
| FR-2/3 (server.py) | Unit | `bin/harness-server` boots; MCP tool list unchanged |
| FR-4 (conftest.py) | Unit | Import the new package from a fresh interpreter; the test suite itself failing to collect is the negative signal if this regresses |
| FR-3 (repo-wide refs) | Integration | Repo-wide grep sweep, excluding `.tickets/completed/` and this ticket's own docs: zero `${CLAUDE_PLUGIN_ROOT}/<old-name>.py` hits |
| FR-5 (tests) | Integration | Full existing pytest suite green — both import errors and literal-string assertion mismatches accounted for and fixed |
| FR-6 (hooks unaffected) | Unit | Grep `hooks/*.py` for an import of any moved module — zero hits before and after the move, confirming no hook needs a change |

## Tradeoffs

- **Chose one flat `lib/` package over per-concern subpackages** because splitting further now (e.g. a `ledger/` for `ticket.py`+`ticket_deps.py`) is speculative design work the ticket doesn't need to do to fix the actual problem.
- **Accepting risk of**: a missed reference in a local, gitignored file (a lead's own notes or an uncommitted script) that the grep sweep can't see, since it only scans tracked content.

## Risks

- Reference count is larger than it first looks: ~40 CLI/prose references plus ~49 test files with direct module imports, some of which additionally assert on old-path *string literals* rather than just importing. Mitigated by the repo-wide (not directory-scoped) grep-verify, run to zero hits before delivery, and by explicitly budgeting for both fix categories in FR-5.
- A reference embedded in markdown prose rather than a fenced code block could be missed by a naive line-based rewrite — mitigated by manually reviewing every match the sweep script reports before committing.

## Implementation Order

1. Create `lib/__init__.py`; `git mv` all 17 modules into `lib/`.
2. Update `server.py`'s imports.
3. Update `conftest.py`'s `sys.path` setup (`pyproject.toml` needs no change — see Components).
4. Repo-wide pattern rewrite of every `${CLAUDE_PLUGIN_ROOT}/<module>.py` reference (includes `context/harness-reference.md`, root `CLAUDE.md`), excluding `.tickets/completed/` and this ticket's own `.tickets/0085-.../` artifacts — historical record, not live references.
5. Update `tests/` imports, and separately fix the two known literal-path-string assertions.
6. Run the full gate suite; fix residual failures.
7. Repo-wide grep-verify zero old-path references remain outside `.tickets/completed/`.
