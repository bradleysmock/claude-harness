# Solution

**Ticket**: 0012
**Title**: Selective Gate Skipping

## Approach

Add an optional `changed_files: list[str] | None` parameter to `gate_run_on_dir` in `server.py`.
Each gate is wrapped in a `GateSpec` dataclass that bundles the gate function with its scope patterns;
a shared `has_scope_match(changed_files, patterns)` helper returns True when overlap exists.
Skipped gates return a `GateResult` with new `skipped=True` and `skip_reason` fields.
The `/gate` command computes `changed_files` via `git diff --name-only HEAD` and passes it as an
explicit parameter. Text-mode (`gate_run` / `run_suite_for`) is out of scope — skip logic is
directory-mode only.

## Components

| Component | Responsibility | Key Interfaces |
|---|---|---|
| `models.GateResult` | Add `skipped: bool = False`, `skip_reason: str = ""`; omit both from `to_dict()` when `skipped=False` | `to_dict()` unchanged for non-skipped results |
| `gates/_scope.py` (new) | `GateSpec(fn: Callable[[str, bool, list[str] \| None], list[GateResult]], scope_patterns: list[str] \| None)`; `has_scope_match(changed_files, patterns) -> bool` | Called by each `run_<lang>_suite_on_dir` dispatch loop |
| `gates/python.py` | Replace bare function list with `list[GateSpec]`; each spec declares `scope_patterns` | `run_python_suite_on_dir(dir, fail_fast, changed_files)` |
| `gates/typescript.py` | Same structure as python.py | Same signature |
| `gates/go.py` | Same structure | Same signature |
| `gates/rust.py` | Same structure | Same signature |
| `gates/__init__.py` | `run_suite_on_dir` threads `changed_files`; `run_suite_for` is unchanged | `run_suite_on_dir(lang, dir, fail_fast, changed_files=None)` |
| `server.py` | `gate_run_on_dir` accepts `changed_files: list[str] \| None`; validates length ≤ 10,000 entries before passing to `run_suite_on_dir`; does NOT call git | MCP tool signature |
| `commands/gate.md` | Document `git diff --name-only HEAD` step before calling `gate_run_on_dir`; handle git failure → pass `changed_files=None`; document SKIP status in findings | `/gate` command spec |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `pathlib.PurePosixPath(f).match(pattern)` for scope matching | Correctly matches `*.py` against `src/foo.py` (suffix match regardless of depth); handles `**` for directory-anchored patterns like `src/**/*.go`; stdlib only |
| `GateSpec` dataclass bundles fn + scope | Eliminates shotgun surgery: adding a gate is one edit in one list; scope cannot drift from the gate it governs |
| `changed_files=None` default | `None` = "caller did not compute a diff" → run all gates. `[]` = "diff computed, zero files" → also run all (FR-3 safe default) |
| `git diff` executed in `commands/gate.md`, not `server.py` | Keeps MCP server's trust surface small; command runs in the worktree context where git is available |
| `skipped`/`skip_reason` omitted from `to_dict()` when `skipped=False` | Preserves existing artifact and JSON contract for all callers that never use `changed_files`; no silent schema drift |
| Skipped gates count as passed for `fail_fast` | A skipped gate is not a failure; the fail-fast loop proceeds to the next gate, which is correct and consistent with `passed=True` |

## Scope Pattern Design

Each `GateSpec` carries `scope_patterns: list[str] | None`. `None` means "no scope declared — never skip."

`has_scope_match` semantics:
- `changed_files` is `None` → return `True` (run gate; no diff info)
- `changed_files` is `[]` → return `True` (run gate; empty diff = unknown state)
- `scope_patterns` is `None` → return `True` (gate has no scope; always run)
- Otherwise → return `any(PurePosixPath(f).match(p) for f in changed_files for p in scope_patterns)`

Example scope patterns per language:
- Python lint/typecheck/test/security: `["*.py", "*.pyi"]`
- TypeScript lint/typecheck/test: `["*.ts", "*.tsx", "*.js", "*.jsx"]`
- Go test/vet/build: `["*.go", "go.mod", "go.sum"]`
- Rust clippy/test/build: `["*.rs", "Cargo.toml", "Cargo.lock"]`

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1 (GateSpec scope) | Unit | Every gate in each language module has a non-None `GateSpec` with `scope_patterns` declared |
| FR-2 (changed_files param) | Unit | `gate_run_on_dir` accepts `changed_files` without error |
| FR-3 (skip on no overlap) | Unit | `has_scope_match(["README.md"], ["*.py"])` → False |
| FR-3 (run on overlap) | Unit | `has_scope_match(["src/foo.py"], ["*.py"])` → True |
| FR-3 (nested path match) | Unit | `has_scope_match(["src/sub/foo.py"], ["*.py"])` → True (pathlib.match semantics) |
| FR-4 (skip result shape) | Unit | Skipped GateResult: `passed=True, skipped=True, skip_reason="no relevant changes"`, `to_dict()` includes skipped/skip_reason |
| FR-4 (non-skipped to_dict) | Unit | Non-skipped GateResult: `to_dict()` does NOT include `skipped` or `skip_reason` keys |
| FR-5 (git diff → /gate) | Integration | Mock `git diff --name-only HEAD` returning markdown paths; verify all source gates SKIP in gate-findings.md |
| FR-5 (git failure fallback) | Unit | `git diff HEAD` non-zero exit, `git diff --cached` also fails → command passes `changed_files=None` → all gates run |
| FR-5 (git cached fallback) | Unit | `git diff HEAD` non-zero exit, `git diff --cached` succeeds with non-empty list → command passes that list |
| FR-6 (no scope = never skip) | Unit | `GateSpec(fn=x, scope_patterns=None)` → `has_scope_match` returns True for any `changed_files` |
| FR-7 (empty diff = run all) | Unit | `has_scope_match([], ["*.py"])` → True |
| FR-7 (None = run all) | Unit | `has_scope_match(None, ["*.py"])` → True |
| FR-8 (findings.md SKIP) | Integration | gate-findings.md contains `**Status**: SKIP` with reason for skipped gates |
| fail_fast + skipped | Integration | fail_fast=True, first gate skipped, second gate fails → second gate result returned, no further gates run |
| Polyglot worktree | Integration | Dir with `.py` + `.ts` files; `changed_files` contains only `.ts` files → Python gates skip, TS gates run; outer response includes `any_skipped: true` |
| NFR-1 (perf budget) | Unit | `has_scope_match` with 10,000-entry `changed_files` and 5 patterns completes in < 10 ms |
| R2-01 (input cap) | Unit | `gate_run_on_dir` with `changed_files` list of > 10,000 entries returns an error response |

## Tradeoffs

- **Chose `pathlib.PurePosixPath.match` over `fnmatch`**: `fnmatch("src/foo.py", "*.py")` returns `False` on paths with directory separators; `PurePosixPath.match` handles this correctly for simple suffix patterns and `**` anchored patterns. Small behavioral difference but critical for acceptance criterion `changed_files=["src/foo.py"]` with pattern `"*.py"`.
- **Chose `GateSpec` dataclass over per-module `SCOPE` dict**: Eliminates a string-keyed indirection layer; scope is co-located with the function reference, not a separately maintained mapping. Risk: slightly more verbose gate declarations; acceptable tradeoff for cohesion.
- **Chose `changed_files=[]` → run all gates**: Distinguishes "caller computed diff, zero files" from "diff unavailable" but both map to safe-run. Simplifies reasoning: `None` is the skip-inhibitor, not `[]`. Documented in FR-3.
- **Accepting risk of**: `to_dict()` omitting `skipped`/`skip_reason` for non-skipped results means a caller that always expects those keys will KeyError. Mitigation: only add the fields to the schema description in `gate-findings.md`; existing callers do not enumerate result keys.
- **Capping `changed_files` at 10,000 entries** to bound the O(n_files × n_patterns × n_gates) match loop within NFR-1's 10 ms budget. A real diff exceeding this limit is treated as `None` (run all gates). This is a safe-fail: the operator pays full gate time for enormous diffs rather than silently skipping.

## Risks

- `pathlib.PurePosixPath.match` pattern semantics changed between Python 3.11 and 3.12 (3.12 added full PEP 428 glob support including `**`). Mitigation: add a test that verifies `PurePosixPath("src/foo.py").match("*.py")` returns True in the project's Python version; if not, fall back to `Path(f).suffix == Path(pattern).suffix` for simple extension patterns.
- Polyglot worktrees: `_detect_stacks` returns multiple languages; each language's gate suite must independently receive `changed_files`. Mitigation: `run_suite_on_dir` already loops over stacks; threading `changed_files` to each stack is additive, not a redesign.
- `commands/gate.md` specifies `git diff --name-only HEAD`. On an initial commit or empty repo, `HEAD` does not exist and git returns an error. Mitigation: command spec must try `git diff --name-only HEAD`; on error, fall back to `git diff --name-only --cached`; on error again, pass `changed_files=None`.

## Implementation Order

1. Extend `models.GateResult` with `skipped: bool = False` and `skip_reason: str = ""`; update `to_dict()` to omit both fields when `skipped=False`. Audit all `to_dict()` call sites in `server.py` (`gate_run`, `gate_run_on_dir`, `repair_run`, `harness_status`) for dict-shape assumptions.
2. Create `gates/_scope.py`: define `@dataclass GateSpec(fn, scope_patterns: list[str] | None)` and `has_scope_match(changed_files: list[str] | None, scope_patterns: list[str] | None) -> bool` with the semantics above.
3. Update `gates/python.py`: replace bare function list with `list[GateSpec]`; declare scope patterns per gate; `run_python_suite_on_dir` accepts `changed_files: list[str] | None`; produce skip results where `has_scope_match` returns False.
4. Repeat step 3 for `gates/typescript.py`, `gates/go.py`, `gates/rust.py`.
5. Update `gates/__init__.py` `run_suite_on_dir` to accept and thread `changed_files`; leave `run_suite_for` unchanged.
6. Update `server.py` `gate_run_on_dir` to accept `changed_files: list[str] | None = None`; pass to `run_suite_on_dir`; update the all-pass and fail-full response shapes: when any gate was skipped, include `"any_skipped": true` in the outer response to let callers distinguish all-skipped from all-passed.
7. Update `commands/gate.md` to document `git diff --name-only HEAD` step, the two fallbacks, and SKIP status in gate-findings.md format.
8. Write all unit tests listed in the Test Plan above.
9. Write integration tests: markdown-only diff and polyglot-partial-change scenarios.
