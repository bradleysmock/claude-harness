# Design: Generalize baseline-delta regression tolerance to all gate languages

**Date:** 2026-07-19
**Status:** Proposed (Checkpoint 1 pending)
**Author:** Bradley + Claude
**Supersedes:** the earlier `regression-gate` draft (2026-06-18), which was written
before ticket 0041 shipped. Most of that draft is now built — see below.

## What changed since the original review

The original "regression gate" gap — *"gates evaluate the artifact, not a diff
against prior passing behavior"* — is **largely closed on current main**:

- **Ticket 0041** replaced changed-file scoping in the TypeScript test gate with a
  **full run + baseline-delta**: run jest `--json`, subtract the merge-base failure
  set (cached under `.harness/test-baselines/` keyed by merge-base SHA, computed in
  a throwaway detached worktree), and fail on the remainder. `GateResult` now
  carries `mode` and `baseline_excluded`, surfaced in `gate-findings.md`.
  (`gates/typescript.py` `_baseline`, `_merge_base_sha`, `_baseline_cache_path`.)
- **Python, Go, and Rust** dir gates already run the **full** suite
  (`gates/python.py:427` `_test_gate_dir` → `pytest … -q`; likewise
  `run_go_suite_on_dir`, `run_rust_suite_on_dir`). So they already *detect* a
  pass→fail regression in an untouched test.

So "did this change break something that previously worked?" is now answered for
every language. The earlier draft's proposed machinery (full run + baseline-delta +
SHA-keyed cache + detached merge-base worktree) is exactly what 0041 built for TS.

## The actual residual

A narrower, real **inconsistency** remains — it is ticket 0041's own declared
out-of-scope item (*"Applying baseline-delta to other languages (follow-up once
proven for TS)"*):

- TS **excludes** pre-existing merge-base failures, so an unrelated already-red
  test does not fail the ticket.
- Python / Go / Rust have **no** such tolerance: because they run the full suite
  with no baseline subtraction, a pre-existing failing test **blocks** an unrelated
  ticket. The polyglot quality bar is therefore uneven in the opposite direction
  from the bug 0041 fixed: TS is now tolerant-and-safe; the others are safe but
  intolerant.

This is a consistency/polish item, not a missing capability. It is worth doing
because uneven behavior across languages is exactly what 0041's problem statement
called out as undermining the polyglot guarantee.

## Goal

Give Python, Go, and Rust the same baseline-delta tolerance TS has: full suite,
minus merge-base failures, fail on the delta — by **extracting 0041's TS logic into
a language-agnostic helper** rather than reimplementing it three times.

## Non-goals

- Changing TS behavior. It is the reference; only refactor if extraction is clean.
- Test-suite performance work (sharding/caching beyond the existing SHA cache).
- Flaky-test arbitration (ticket 0026's domain). Flakes surface as
  `baseline_excluded` lines, as they do for TS today.

## Approach

### 1. Extract a shared baseline-delta harness

Lift the language-neutral parts of `gates/typescript.py` into a
`gates/_baseline.py` helper:

- `merge_base_sha(root, base) -> str | None`
- `baseline_cache_path(root, sha)`, `read_baseline_cache`, `write_baseline_cache`
  (the `.harness/test-baselines/` SHA-keyed store — already generic).
- `compute_delta(current_failing: set[str], baseline_failing: set[str]) -> Delta`
  returning new failures (fail the gate) and `baseline_excluded` (report only).
- `run_in_detached_baseline_worktree(root, sha, run_suite)` — the throwaway
  detached-worktree pattern 0041 uses, so the baseline run never touches the ticket
  worktree.

The **only** language-specific input is a `failing_test_ids(directory) -> set[str]`
function that runs that language's suite and returns stable per-test IDs:

- Python: `pytest --json-report` (or `-q` + node-id parse), IDs like
  `tests/test_x.py::test_y`.
- Go: `go test -json`, IDs like `pkg/path.TestName`.
- Rust: `cargo test -- -Z unstable-options --format json` (or the stable
  `--format=json` where available), IDs like `crate::mod::test_name`.

### 2. Wire each language's `_test_gate_dir` through the helper

Each becomes: collect current failing IDs → if a merge base exists, subtract the
cached baseline (compute on cache miss in the detached worktree) → fail on the
delta, attach `baseline_excluded` and `mode` to the `GateResult`. When git is
absent or the base is unknown, fall back to **strict full-suite** (same fail-closed
fallback 0041 uses) — never silently pass.

### 3. Removed-test detection (small add, all languages)

Extend `compute_delta` to also flag IDs present-and-passing at baseline but **absent**
in the current collection (`pass→removed`) — a deleted previously-green test is a
regression the failure-set diff alone misses. Reported alongside new failures.

### 4. Record resolved regressions into memory

When a delta failure is repaired, `memory(action="record", ..., gate="test",
outcome="passed", resolution=...)`. This is already the flow for gate repairs; it
means baseline-delta regressions become part of the corpus and (given the
companion `memory-forward-injection` design) can be pre-empted on later specs.

## Files to change

Engine:

1. New `gates/_baseline.py` — extracted SHA cache, merge-base, delta, detached
   worktree runner.
2. `gates/typescript.py` — refactor `_test_gate_dir` onto the shared helper (behavior
   unchanged; this is the "prove the extraction is faithful" step).
3. `gates/python.py`, `gates/go.py`, `gates/rust.py` — `_test_gate_dir` /
   `run_*_suite_on_dir` route through the helper with a language-specific
   `failing_test_ids`.
4. `models.py` / `gates/__init__.py` — `baseline_excluded` / `mode` already exist on
   `GateResult`; ensure the polyglot aggregator (`gate_run_on_dir`) preserves them
   per stack.

Prompt/flow:

5. `context/harness-reference.md` — gate-suite section: baseline-delta now applies
   to all four languages, not just TS.

## Verification

Reuse 0041's test shape (`tests/test_0041_ts_baseline_delta.py`) per language:

1. **pass→fail detected:** broken untouched test on a fixture worktree fails the
   gate (Python/Go/Rust).
2. **baseline excluded:** a test failing at the merge base does **not** fail the
   ticket; it appears as a `baseline_excluded` line.
3. **pass→removed detected:** a previously-green test deleted in the worktree is
   flagged.
4. **strict fallback:** git absent / unknown base → full-suite, fail-closed.
5. **TS unchanged:** the refactor leaves every existing 0041 test green.

## Recommendation

Lower priority than `memory-forward-injection`: this is cross-language *consistency*
for an already-working capability, whereas forward-injection adds a capability the
harness does not have. If the baseline-delta inconsistency is not biting real
polyglot tickets, this can wait — or be folded into a routine gate-consistency
ticket rather than carried as a standalone design.
