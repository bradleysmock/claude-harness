# Solution

**Ticket**: 0036
**Title**: Parallel gate execution

## Approach

Introduce a `GateScheduler` class in `gates/scheduler.py` that accepts a gate list with a dependency graph (`gates/gate_graph.py`) and a concurrency limit, then drives execution via a `ThreadPoolExecutor` — no asyncio layer; the gate functions are synchronous subprocess calls and a thread pool is sufficient. Each language runner's directory-mode entry point (`run_*_suite_on_dir`) is refactored to delegate to `GateScheduler` rather than a sequential loop. Per-gate log files are written on gate completion. A unified result list is returned as before; `gate-findings.md` generation is unchanged.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| `gates/gate_graph.py` | `GATE_GRAPH: dict[str, list[str]]` per language (gate → prerequisites); `validate_dag(graph)` raises `ValueError` on cycles | `PYTHON_GATE_GRAPH = {"test": ["type_check"]}` (lint, security, type_check independent); `GO_GATE_GRAPH = {"test": ["build"], "vet": []}` etc. — all four defined before any runner is modified |
| `gates/scheduler.py` | `GateScheduler(gates: list[str], gate_graph: dict[str, list[str]], max_workers: int \| None, log_dir: Path)`: executes gates in dependency order via `ThreadPoolExecutor`; skips dependents on failure; catches exceptions as `TOOL_ERROR`; writes per-gate log on completion; emits structured log entry per gate (name, status, duration_ms, log_path) | `GateScheduler.run(directory: str) -> list[GateResult]` — returns results in topological declaration order, not completion order; accepts injectable `_clock: Callable[[], float]` for test seams |
| `gates/log_writer.py` | `LogWriter(log_dir: Path)`: `write(gate_name: str, content: str) -> Path` — resolves final path, asserts containment within `log_dir` via `Path.relative_to()`, raises `ValueError` on traversal attempt | `write(gate_name: str, content: str) -> Path` |
| `gates/python.py` (modified) | Replace sequential loop in `run_python_suite_on_dir` with `GateScheduler`; `run_python_suite` (text mode) is **not modified** | no public interface change |
| `gates/typescript.py`, `go.py`, `rust.py` (modified) | Same pattern as python.py | no public interface change |
| `server.py` (modified) | Read `parallel_gate_limit` from `_standards.md` config (if present); pass to `run_suite_on_dir` | no MCP tool signature change |

## Tech Choices

| Choice | Rationale |
|---|---|
| `ThreadPoolExecutor` directly, no asyncio layer | Gate functions are synchronous subprocess calls; asyncio + `run_in_executor` layers async machinery on top of threads without benefit. Direct `ThreadPoolExecutor` is simpler and equally correct (D-03 addressed). |
| `Future.result()` with exception catch per gate | Each submitted future is checked individually; an exception in one gate is caught, converted to `TOOL_ERROR`, and sibling futures are still awaited. No `gather` ambiguity (D-01 addressed). |
| `contextvars.copy_context().run(gate_fn, directory)` as the executor callable | Propagates run-ID / ticket-ID context vars from the calling thread into each worker thread (D-10 addressed). `copy_context()` is a shallow, non-raising operation; no error handling required at the call site. |
| Log written on gate completion (not incremental) | `subprocess.run` with `capture_output=True` buffers output; incremental write would require `Popen` + `readline()`. Per-gate log files are still written before `gate-findings.md`, so a crash in one gate still leaves its peers' logs intact. Text mode (`run_python_suite`) continues using `capture_output=True` and is unaffected. |
| All four language `GATE_GRAPH`s defined in step 1 | Pins the `dict[str, list[str]]` interface before any runner commit depends on it; prevents step-5 rework (D-04 addressed). |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|---|---|---|
| FR-1 | Unit | `GateScheduler` with injectable `_clock` records `(gate, start, end)`; two independent gates have overlapping intervals |
| FR-2 | Unit | When `type_check` fails, `test` is skipped; result list contains a skip-status `GateResult` |
| FR-3 | Unit | Log file created per gate under `log_dir`; contains gate's stdout+stderr content |
| FR-3 (path safety) | Unit | `LogWriter.write("../../etc/evil", ...)` raises `ValueError` (D-02 addressed) |
| FR-4 | Integration | `gate-findings.md` content from parallel run equals sequential run for same directory |
| FR-5 | Unit | `max_workers=1` dispatches gates in strictly serial order matching dependency chain |
| FR-6 | Unit | `security` gate fails; has no dependents; `fail_fast=True` stops scheduler after `security` completes without waiting for in-flight siblings (D-06 addressed) |
| FR-7 | Unit | Structural overlap test via injectable clock (not wall-clock timing; avoids flakiness) (D-05 addressed) |
| FR-8 | Unit | `max_workers=1` + `fail_fast=True`: first failing gate stops the run; result list is identical to current sequential loop's early-return behavior (D-06 addressed) |
| FR-6 (fail_fast) | Unit | `fail_fast=True`: two independent gates submitted; first completes with failure; scheduler submits no additional gates; already-submitted in-flight gate still runs to completion; both results captured in returned list (D-13) |
| FR-8 (large output) | Unit | Gate returns 1 MB of stdout; `LogWriter.write` produces a log file of the correct byte count; `GateResult` is not truncated (D-15) |
| NFR-1 | Unit | Gate function raises unhandled exception; sibling gates complete; exception surfaces as `TOOL_ERROR` in results |
| NFR-3 | Unit | Cycle in `GATE_GRAPH` raises `ValueError` at `validate_dag()` call |

## Tradeoffs

- **Chose `ThreadPoolExecutor` over asyncio + `run_in_executor`**: removes the `asyncio.run()` / existing-loop ambiguity entirely. Accepting: slightly less idiomatic for future async integrations, but the gate layer is explicitly synchronous and subprocess-bound.
- **Chose post-completion log write over incremental `Popen` streaming**: reduces implementation complexity. Accepting: log is empty if the gate process is killed mid-run (SIGKILL edge case); documented in `harness-reference.md`.
- **Chose `return_exceptions`-equivalent pattern (per-future exception catch) over `asyncio.gather`**: eliminates the gather failure-mode ambiguity entirely since asyncio is not used.
- **Chose static `GATE_GRAPH` per language, not user-configurable graph**: avoids operator misconfiguration risk. `_standards.md` only controls `parallel_gate_limit`. Operators cannot reorder gate phases without code changes.
- **`run()` returns results in topological declaration order**: callers (including `gate-findings.md` generation) iterate by position and must not encounter unpredictable gate ordering. Completion order is tracked internally but results are sorted before return.

## Risks

- Thread safety of gate functions: they write to temp dirs, not shared state. No shared mutable state in current implementation. Residual risk: if a gate function is later modified to write shared state, the scheduler won't protect it.
- `contextvars.copy_context().run(fn, arg)` incurs a shallow context copy per gate. At 4 gates, this is negligible.
- `text mode` (`run_python_suite`) is explicitly excluded from this change. Future tickets that add parallelism to text mode will find `GateScheduler` reusable but must handle the temp-dir lifecycle differently.
- **fail_fast semantic contract**: `fail_fast=True` prevents submission of new futures after a gate failure. It does **not** cancel already-submitted in-flight futures (`Future.cancel()` cannot stop a running thread). The scheduler must call `.result()` on all submitted futures before returning, so their results (including any exceptions converted to `TOOL_ERROR`) appear in the returned list. Result list always reflects the complete set of submitted gates.

## Implementation Order

1. Add `gates/gate_graph.py` — define `GATE_GRAPH` for all four languages (Python, TypeScript, Go, Rust); add `validate_dag()`; add unit tests for cycle detection and all four language graphs. **No runner is modified in this step.**
2. Add `gates/log_writer.py` — `LogWriter` with path-containment guard; unit tests including traversal-attack case.
3. Add `gates/scheduler.py` — `GateScheduler` with `ThreadPoolExecutor`, per-future exception catch, skip propagation, `fail_fast` support, injectable clock seam; unit tests for all test plan scenarios above.
4. Refactor `gates/python.py` — replace sequential loop in `run_python_suite_on_dir` with `GateScheduler(PYTHON_GATE_GRAPH, ...)`; verify all existing `run_python_suite_on_dir` tests pass unchanged; `run_python_suite` untouched.
5. Refactor `gates/typescript.py`, `go.py`, `rust.py` — same pattern; reuse `GateScheduler`.
6. Modify `server.py` — read `parallel_gate_limit` from `_standards.md` (if present); pass to `run_suite_on_dir` as `max_workers`.
7. Integration test: `gate-findings.md` equivalence test (parallel vs. sequential output); structural overlap test with real gate functions as smoke test (labeled non-deterministic, skipped in CI by default).
8. Update `context/harness-reference.md` with `parallel_gate_limit` config key and log-write-on-completion caveat.
