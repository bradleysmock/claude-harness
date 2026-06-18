# Design: Regression-aware gate (artifact-vs-prior-behavior)

**Date:** 2026-06-18
**Status:** Proposed (Checkpoint 1 pending)
**Author:** Bradley + Claude

## Problem

Every gate the harness runs evaluates the artifact against the **spec**:
type/lint/test/security in `gate_run` / `gate_run_on_dir`, the critic against the
ticket baseline. None of them ask the distinct question: *"did this change break
something that previously worked?"* The closest thing is a spec-quality heuristic
(`harness-full/.../scorer.py:117` rewards a spec that *contains* a "still pass"
criterion) — but that just nudges the author to write a test; it runs no
diff-against-baseline.

"Is the code correct/aligned with its spec" and "did it regress prior passing
behavior" are independent checks. A change can be perfectly spec-compliant and
still break an unrelated, previously-green test. The harness has no gate for the
second question.

## Goal

Add a regression gate to the **ticket** build path (where a worktree runs against
a real project with a real existing test suite, i.e. a real baseline), that fails
the build when a previously-passing test goes pass→fail or disappears — and
routes those failures into the existing repair loop.

## Non-goals

- Spec mode (`build-spec.md`). It builds a single artifact in a temp dir with no
  surrounding project, so there is no prior-behavior baseline to regress against.
  Regression is ticket-mode only.
- Re-implementing test running. Reuse the per-language gate machinery in `gates/`;
  the regression gate is a *diff over test results*, not a new runner.
- Flaky-test arbitration. A test that flakes between baseline and current is the
  project's problem; we report it as a candidate regression and let the lead judge.

## Why ticket mode, and what "baseline" means

In `build-ticket.md`, Step 2 creates a worktree off `main`. `main` (the worktree's
fork point) is the **baseline**: the set of project tests that pass *before* this
ticket's changes. The worktree tip after Step 5's commit is the **current** state.
A regression is any test in `baseline_pass ∖ current_pass` — i.e. it passed on
`main` and now fails or no longer exists.

Tests that are **new** in the worktree are out of scope here — their correctness is
the integration gate's job (Step 4e). Tests that **already failed** on `main`
(pre-existing breakage) are not regressions. Only pass→fail and pass→removed count.

## Approach (chosen: one-time baseline capture + result-diff tool)

### 1. Capture the baseline once, at worktree creation

Extend `build-ticket.md` **Step 2**: immediately after the worktree is created,
run the project's existing test suite against the **baseline** (a detached check
of `main`, or equivalently the project root before any worktree write) and persist
the passing test-id set to `.harness/baselines/XXXX-<slug>.json`:

```json
{"ticket": "XXXX-<slug>", "ref": "main",
 "passing": ["tests/test_auth.py::test_login", "..."],
 "captured": "<iso8601>"}
```

One capture per build. Repair rounds reuse it, so the baseline suite is not re-run
on every attempt. If `main`'s suite does not fully pass at capture time, that is
fine — we record only the *passing* subset, which is exactly the set we must not
regress.

### 2. New tool: `regression_check`

`regression_check(directory, language, project_root, baseline_path)` →

- Runs the **existing project test suite** in `directory` (the worktree),
  collecting per-test pass/fail node IDs (not just an aggregate). First cut:
  Python via `pytest --tb=no -q -rN` node-id parsing (or `--co` + result map),
  mirroring `gates/python.py`. Other languages extend per the existing
  per-language gate module pattern (`go test -json`, `vitest --reporter=json`,
  `cargo test --format json`) — each lands as the gate languages are needed.
- Loads `baseline_path`'s passing set `B` and computes the current passing set `C`.
- **Regressions** = `B ∖ C`, classified per id as `pass→fail` or `pass→removed`.
- Returns JSON consistent with `gate_run_on_dir`:
  - clean: `{"passed": true, "checked": <len B>, "regressions": []}`
  - dirty: `{"passed": false, "regressions": [{"test": "...", "kind": "pass->fail",
    "errors": [...]}], "baseline_ref": "main"}`

The per-test `errors` reuse the `GateError` shape (`models.py`) so regression
findings flow into the repair loop with the same structure gate failures already
have.

### 3. New build step: regression gate after the build, before review

Insert **Step 5.5** in `build-ticket.md`, after the Step 5 worktree commit and
before the Step 6 diff:

1. Call `regression_check(".worktrees/XXXX-<slug>", "auto", project_root,
   ".harness/baselines/XXXX-<slug>.json")`.
2. **If `passed`** → continue to Step 6 (diff + critic), unchanged.
3. **If regressions** → enter the existing repair loop (same shape as Step 4e):
   - `memory(action="retrieve", ...)` on the regression error text.
   - Fix the worktree at the implicated `file:line`.
   - Re-run `regression_check` (baseline is cached — only the current suite re-runs).
   - Repeat up to `MAX_REPAIR_ATTEMPTS`.
4. **If still regressing** after the cap → set `status: changes-requested`, surface
   the residual regressions to the lead (which prior-passing tests broke, and what
   each repair round tried), exactly like Step 7d's exhaustion handling.

A regression then becomes the same first-class, repair-driving signal a gate
failure is — the only new thing is *what* it checks.

### 4. Memory: record regressions too

On a resolved regression, `memory(action="record", ..., gate="regression",
outcome="passed")`. This makes broken-then-fixed regressions part of the corpus,
so the forward-injection design (`2026-06-18-memory-forward-injection-design.md`)
can pre-empt them on later specs in the same area. The two designs compose.

## Cost control

The baseline suite runs **once** per build (Step 2). The current suite runs once
per regression-check, i.e. once per repair round — the same order of cost as the
integration gate, which already re-runs tests each round. For large suites, an
optional `REGRESSION_SCOPE` config (paths/markers, default = full suite) bounds
what is collected. Default stays full-suite: it is the cheap, correct baseline and
matches the "slots beside the existing gates" intent.

## Alternatives considered and rejected

- **Fold into `gate_run_on_dir`.** Regression needs a baseline ref and a result
  *diff*, which the stateless gate runner has no place for. A distinct tool keeps
  `gate_run_on_dir` simple and makes the new check explicit in the flow.
- **Run regression per spec inside Step 4e.** Premature: intermediate specs in a
  DAG legitimately leave the suite red until the layer completes. Checking once
  after the full build (Step 5.5) avoids false regressions mid-DAG.
- **Diff against the prior artifact instead of `main`.** The prior artifact is the
  spec's own previous attempt, not "prior passing behavior of the project." `main`
  is the correct baseline.

## Files to change

Engine:

1. New `gates/regression.py` (or `regression.py`) — suite runner with per-test
   result collection + baseline diff; first cut Python, extension points for the
   other gate languages.
2. `server.py` — new `regression_check(...)` tool; a `baseline_capture(...)` tool
   (or fold capture into `gate_run_on_dir` with a `capture_baseline` flag) writing
   `.harness/baselines/`.
3. `.gitignore` — ignore `.harness/baselines/` (ephemeral, like `results/`).

Prompt/flow (project-root copies, per `CLAUDE.md`):

4. `context/flows/build-ticket.md` — Step 2 baseline capture; new Step 5.5
   regression gate + repair loop; Step 7d-style exhaustion handling.
5. `context/harness-reference.md` — document the regression gate in the gate-suite
   and repair-loop sections; note it is ticket-mode only.
6. `README.md` — add the regression gate to the gate catalog.

## Verification

Unit tests (`tests/`):

1. **pass→fail detected:** baseline has `test_x` passing; current run has it
   failing → reported as `pass->fail`, `passed=false`.
2. **pass→removed detected:** baseline has `test_x`; current suite no longer
   collects it → reported as `pass->removed`.
3. **new-failing ignored:** a test absent from baseline that fails now is **not** a
   regression (integration gate's domain).
4. **pre-existing-failure ignored:** a test failing in *both* baseline and current
   is not a regression.
5. **clean pass:** identical pass sets → `passed=true`, empty regressions.

Flow-level dry run on a ticket whose change deliberately breaks one unrelated
previously-green test: confirm Step 5.5 catches it, the repair loop engages, and —
when left unrepaired — the build lands in `changes-requested` with the broken test
named.
