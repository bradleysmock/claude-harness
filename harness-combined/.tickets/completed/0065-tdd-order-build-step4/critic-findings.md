# Critic Findings — 0065-tdd-order-build-step4

## Round 1 — 2026-07-20

Active panels: Core (always active) + Python (`**/*.py` files in scope, `pyproject.toml` present) + Testing (`tests/**` in scope). No TypeScript/Go/Rust panel — the changed files are all `.py`/`.md`; `gates/typescript.py` is Python source, not a `.ts`/`.tsx`/`.js` file, so the TS panel trigger doesn't fire even though the module's *subject* is TypeScript tooling. No HTTP/API, CI/CD, or other panels triggered by this file set.

No `gate-findings.md` exists for this ticket (gate suite was run directly via pytest/ruff/mypy rather than through the `gate_run_on_dir` MCP tool, per this repo's established monorepo workaround); Step 2 skipped as instructed.

### Findings

**BLOCKER** — Core / Dimension 8 (McGraw, fail-closed) + Step 2.5 (solution alignment) · `server.py:604-619`
`gate_run_red_check` only caught `RedGateError`, letting any other exception from `check_red`/`next_action` propagate uncaught out of the MCP boundary — contradicts solution.md's Components table, requirements FR-9, and the tool's own docstring, all of which promise every exception is contained as `tool_error`. `tests/test_0065_gate_run_red_check.py` only exercised the `RedGateError` path, so the gap shipped untested.
**Status: FIXED** — widened the except clause to `(RedGateError, ValueError, TypeError, AttributeError, KeyError, IndexError, OSError, RuntimeError)`; added `test_generic_exception_from_check_red_is_contained_as_tool_error` (monkeypatches `check_red` to raise `RuntimeError`).

**BLOCKER** — Core / Dimension 8 (correctness) + Step 2.5 (solution alignment) · `gates/red_gate.py:156-163`
`_check_go` ran across the entire module (`./...`) and matched present ids by bare function name (`p.rsplit(".", 1)[-1] == w`), never receiving `test_file`. Go test names collide across packages routinely; a same-named, already-passing test in an unrelated package would misattribute a `blocking` target as `red`, defeating the ticket's core purpose. Untested for multi-package collisions.
**Status: FIXED** — `_check_go` now takes `test_file`, scopes the `go test` invocation to the target's own package directory (never `./...`), and the matcher keeps the package qualifier (`p.endswith("." + w)`). Added `test_go_collision_cross_package_same_test_name_not_misattributed` (two packages, same test name, one pre-existing failure) proving the fix.

**MAJOR** — Testing / Dimension 22 (Dodds, Feathers) + Step 2.5 (Test Plan: FR-10) · `tests/test_red_gate.py`
Collision-attribution scenario (FR-10, FR-3) was tested only for Python; Go/Rust/TypeScript had only basic RED/BLOCKING happy-path coverage, letting the Go matcher bug above ship unverified.
**Status: FIXED** — added `test_go_collision_cross_package_same_test_name_not_misattributed`, `test_rust_collision_target_passes_while_unrelated_module_test_of_same_name_fails`, `test_typescript_collision_target_passes_while_unrelated_test_in_same_file_fails`.

**MAJOR** — Testing / Dimension 22 + Step 2.5 (Test Plan: "crashed runner → tool_error") · `gates/red_gate.py:235-238`
The `except subprocess.TimeoutExpired` / `except OSError` branches (the "crashed runner" classification path) were never exercised by any test.
**Status: FIXED** — added `test_python_tool_error_on_runner_timeout` and `test_python_tool_error_on_runner_os_error` (monkeypatch `_py._exec_dir`).

**MAJOR** — Core / Dimension 4 (documentation accuracy) + Step 2.5 (requirements FR-4/FR-6) · `context/flows/build-ticket.md:186`
Sub-step d's `blocking` → `retry` branch never stated how `attempt` is tracked/incremented across the loop, unlike Step 4f/7a's explicit `For each attempt N (1 … MAX_REPAIR_ATTEMPTS):` framing — risking an unbounded loop or an unenforced retry budget in execution.
**Status: FIXED** — sub-step d now opens with "For attempt `N` (1 … `MAX_REPAIR_ATTEMPTS`):" and the `retry` bullet explicitly says "re-run this sub-step as attempt `N+1`".

**MINOR** — Core / Dimension 6 (Hyrum's Law / contract precision) · `gates/red_gate.py:166-182`
`_check_rust`'s per-node_id loop returns early with a single-element `node_ids` tuple on the first unparseable node, silently discarding already-aggregated `present`/`failing` data and truncating `result.node_ids` relative to the caller's full request.
**Status: not auto-fixed (MINOR, per severity policy)** — logged for the lead.

**MINOR** — Core / Dimension 3 (naming precision) · `gates/red_gate.py:225` (now ~232)
`_contained(...)` is called purely for its raise side-effect; the resolved `Path` it returns is discarded, which could mislead a reader expecting the resolved path to be threaded through.
**Status: not auto-fixed (MINOR, per severity policy)** — logged for the lead.

**OBS** — `context/flows/build-ticket.md:187,232-235`
Sub-step d promises "Note the skip; it surfaces in the Step 6/7 summary" for `escalate_skip` outcomes, but Step 6's diff-summary bullets don't explicitly name red-gate-escalated/skipped specs.
**Status: not auto-fixed (OBS, per severity policy)** — logged for the lead.

## Round 2 — 2026-07-20

Independent re-review (not a checklist re-check) of the current code after round 1's repair. Both round-1 BLOCKERs verified genuinely fixed. No new BLOCKERs. Two new MAJOR findings surfaced by the repair itself; one MINOR (docstring precision on the exception tuple, not a functional gap).

### Findings

**MAJOR** — Core / Dimension 4 + Testing / Dimension 22 · `gates/red_gate.py` (check_red docstring) + `tests/test_red_gate.py` (TypeScript section)
`check_red`'s docstring documented TypeScript `node_ids` as "bare test title(s) (jest fullName)" — self-contradictory. The actual matcher (`p.endswith("::" + w)`) and the anchored jest `-t` pattern both require the **full** describe-path-qualified `fullName`; a bare title under a `describe()` block would select zero tests, most likely misclassifying as `tool_error` instead of `red`/`blocking`. Every round-1 TypeScript test used a flat top-level `test(...)` with no `describe()`, so the discrepancy never surfaced.
**Status: FIXED** — corrected the docstring in both `check_red` and the `gate_run_red_check` MCP tool; added `test_typescript_node_id_is_the_full_describe_qualified_name` (a `describe()`-wrapped target test, RED case) that pins the real contract.

**MAJOR** — Core / Dimension 6 (Hyrum's Law) · `gates/red_gate.py` (`_check_go` package-dir derivation)
`_check_go`'s package-directory scoping (round 1's fix) derived `pkg_dir` from the raw, unrelativized `test_file` — not the already-resolved, worktree-contained path `_contained()` computes. For an absolute `test_file` (a documented-valid input per `check_red`'s own contract), this produced a malformed `go test` target, risking a spurious `TOOL_ERROR` or a false `RED` that never ran the target test.
**Status: FIXED** — `check_red` now relativizes `test_file` via the resolved path before dispatching to each per-language check (this also resolves round 1's still-open MINOR about the resolved path being discarded). Added `test_go_red_with_absolute_test_file_path`.

**MINOR** — `server.py` docstring
The docstring said "any exception … is caught here" but the except clause enumerates a specific tuple (required by this repo's `pre_write_guard` hook, which blocks a bare `except Exception:`). The wording overstates the guarantee slightly.
**Status: not auto-fixed (MINOR, per severity policy)** — logged for the lead.

Round 1's two MINORs and one OBS remain open (unchanged, logged for the lead — not required).

## Round 3 — 2026-07-20

Independent re-review. All round-1/round-2 fixes re-verified as genuinely holding (not taken on faith) — no regressions in prior fixes.

### Findings

**BLOCKER** — Core / Dimension 8 (McGraw, trust boundaries) + Step 2.5 (solution alignment) · `gates/red_gate.py` (`_check_python`)
`check_red` validated only `test_file` for worktree containment; `node_ids` was never validated. Python `node_ids` are full pytest node ids (`path::test`) — a second, independent path input passed straight into pytest's argv via `_check_python`. A crafted `node_id` (e.g. a `../../` traversal or an absolute path) would reach pytest unfiltered, letting it collect/execute a file outside the worktree root — exactly the class of escape `_contained()` exists to prevent, applied to the wrong/incomplete set of inputs.
**Status: FIXED** — `_check_python` now validates each `node_id`'s leading path segment (split on `::`) through `_contained()` before dispatch. Added `test_check_red_rejects_python_node_id_whose_path_escapes_worktree`.

### No other findings

No new findings beyond the one BLOCKER above. Round 1's two still-open MINORs and one OBS remain unchanged, logged for the lead, not required.

## Round 4 — 2026-07-20

Independent re-review, scrutinizing every per-language path in `check_red` for the same class of input-validation gap round 3 found. Round 3's fix confirmed genuinely holding (traced the call path). No equivalent path-injection surface found in the Go/Rust/TypeScript branches (none embed a filesystem path in `node_ids` the way pytest's `path::test` does). **No BLOCKER or MAJOR findings this round — repair succeeded (attempt 3 of `MAX_REPAIR_ATTEMPTS`=3).**

### Findings

**MINOR** — Core / Dimension 4 (documentation accuracy) · `gates/red_gate.py` (`check_red` docstring)
The docstring's "Raises `RedGateError` **only** for..." enumeration wasn't updated when round 3 added a fourth raising path (a Python node_id's own path segment escaping the worktree). Low functional impact — logged for the lead, not auto-fixed (MINOR).

Round 1's two still-open MINORs and one OBS remain unchanged, logged for the lead, not required.
