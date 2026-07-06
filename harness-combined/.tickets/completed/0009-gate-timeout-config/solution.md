# Solution

**Ticket**: 0009
**Title**: Gate timeout configuration

## Approach

Add a `GateTimeoutConfig` dataclass to `gates/__init__.py` that is populated from `.harness.toml` using `tomllib` (Python stdlib ≥ 3.11, with `tomli` fallback for 3.10). Each language gate module accepts an optional `GateTimeoutConfig` parameter and uses it to resolve the timeout for each gate type, falling back to existing hardcoded values when `None`. The MCP server auto-detects `.harness.toml` in the target directory (or `project_root` for text-mode) and passes the loaded config into the suite runner.

## Components

| Component | Responsibility | Key interface |
|---|---|---|
| `GateType` (gates/__init__.py) | `Literal["lint", "typecheck", "test", "security"]` alias for type-safe gate naming | Used by `timeout_for()` |
| `GateTimeoutConfig` (gates/__init__.py) | Holds per-gate and global timeout values; provides `timeout_for(gate: GateType) -> int` resolver; classmethods `load(path: Path) -> GateTimeoutConfig` and `from_directory(directory: Path) -> GateTimeoutConfig \| None` | `load()` returns instance with all-None timeout fields if file has no timeout keys (file-present-but-unconfigured); raises `ValueError` wrapping `TOMLDecodeError` with filename on malformed TOML; raises `ValueError` on non-positive timeout values; silently ignores unknown keys. `from_directory()` returns `None` when `.harness.toml` is absent (file-absent — distinct sentinel from all-None-field instance) |
| `_timeout_error(gate, timeout_s)` (gates/__init__.py — shared) | Returns `GateResult` with `code="TIMEOUT"` and message `"<gate> gate timed out after <N> s"` | Shared by all language modules; removes four duplicates |
| Updated `run_python_suite`, `run_python_suite_on_dir` (gates/python.py) | Accept `config: GateTimeoutConfig \| None = None`; call `config.timeout_for(gate_type)` before each subprocess call | Same pattern for typescript.py, go.py, rust.py |
| `run_suite_for`, `run_suite_on_dir` (gates/__init__.py) | Accept and forward `config: GateTimeoutConfig \| None = None` | No change to callers that omit the param |
| `server.py` `gate_run` / `gate_run_on_dir` handlers | Text-mode `gate_run`: load `.harness.toml` from `project_root`; dir-mode `gate_run_on_dir`: load from target `directory`; pass loaded config to suite functions | No change to MCP caller interface |

## Tech Choices

| Choice | Rationale |
|---|---|
| `tomllib` (stdlib) + `tomli` fallback | Zero mandatory new dependency; `tomllib` available 3.11+; `tomli` is the reference implementation for 3.10 |
| `.harness.toml` dedicated file over `_standards.md` embed | Machine-readable without Markdown parsing; consistent with Cargo/pyproject patterns |
| `GateType` as `Literal[...]` | Surfaces gate-name typos at type-check time; no runtime overhead vs `str` |
| Single `GateTimeoutConfig.from_directory(path)` module entry point | Hides `.harness.toml` path construction; consistent with single-responsibility; `load(path)` retained as lower-level testable method |
| `subprocess.run(timeout=N)` (not manual `Popen`) | `subprocess.run` calls `proc.kill()` + `proc.wait()` on `TimeoutExpired` before re-raising, guaranteeing no orphaned child processes; do not replace with `Popen`-based polling |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|---|---|---|
| FR-1 | Unit | `.harness.toml` present + valid → config loaded |
| FR-1 | Unit | `.harness.toml` absent → `from_directory()` returns `None` |
| FR-1 | Unit | Malformed TOML → `ValueError` raised with filename in message |
| FR-1 | Unit | Unknown/extra TOML keys → silently ignored, no error |
| FR-1 | Unit | Float value (e.g., `test_timeout_seconds = 30.5`) → truncated to `int` |
| FR-2/FR-3 | Unit | `timeout_for("test")` returns `test_timeout_seconds` when set; falls back to `default_timeout_seconds`; falls back to hardcoded default |
| FR-3 | Unit | Per-gate override beats global default beats hardcoded |
| FR-4 | Unit | `_timeout_error("lint", 30)` message = `"lint gate timed out after 30 s"` |
| FR-4 | Integration | Patch `subprocess.run` to raise `TimeoutExpired(cmd=[], timeout=5, output=b"", stderr=b"")`; call `run_python_suite` with `config(test_timeout_seconds=5)`; assert `GateResult.code == "TIMEOUT"`, `GateResult.passed == False`, and message == `"test gate timed out after 5 s"` |
| FR-4 | Integration | Same pattern for typescript, go, rust suites (parametrize across all four to prevent silent config-forwarding regressions) |
| FR-5 | Unit | `config=None` → existing hardcoded defaults applied, behavior unchanged |
| FR-7 | Unit | `server.py gate_run_on_dir`: `.harness.toml` present in target dir → config loaded and passed to `run_suite_on_dir` |
| FR-7 | Unit | `server.py gate_run` (text-mode): `.harness.toml` present in `project_root` → config loaded and passed to `run_suite_for` |
| FR-7 | Unit | `server.py gate_run` (text-mode): `.harness.toml` absent in `project_root` → `run_suite_for` called with `config=None` (regression guard for FR-5) |
| C-04 | Unit | `default_timeout_seconds = 0` → `ValueError` at load time |
| C-04 | Unit | `test_timeout_seconds = -1` → `ValueError` at load time |
| C-08 | Unit | File present but no timeout keys → all `timeout_for()` calls return hardcoded defaults |
| FR-6 | — | xref requirements.md FR-6 |

## Tradeoffs

- **Chose `subprocess.run` over `Popen` + manual kill**: `subprocess.run` performs `proc.kill(); proc.wait()` inside the `TimeoutExpired` handler before re-raising, so no orphaned child processes. This is a correctness invariant — any future refactor to `Popen` must replicate the kill/wait idiom.
- **Timeout message `"<gate> gate timed out after <N> s"` is a stable human-readable contract**: structured `code="TIMEOUT"` is the machine-readable signal; the message is for operators. Treat any format change as semver-significant.
- **Float TOML values truncated (not rejected)**: `int(float_val)` at load time is more permissive than strict type enforcement; the alternative is a `ValueError` for `30.5`. Accepting truncation reduces friction.
- **Unknown TOML keys silently ignored**: consistent with how `pyproject.toml` tools handle unrecognized sections; any key not in the known set is discarded.

## Risks

- `tomllib` stdlib requires Python 3.11. The project's `pyproject.toml` has no `[project]` table, so PEP 508 dependency markers cannot be used. Mitigation: inline `try: import tomllib except ImportError: import tomli as tomllib` in `gates/__init__.py`; add `tomli` to `requirements.txt` for environments on Python < 3.11.
- Four language modules each duplicate `_timeout_error`. Consolidating to `gates/__init__.py` must happen in step 1 before module edits; otherwise steps 3–5 will edit code that is immediately deleted.

## Implementation Order

1. Write failing tests for `GateTimeoutConfig.load()`, `from_directory()`, `timeout_for()`, `_timeout_error()` (unit tests covering all FR-1 through FR-5 rows above).
2. Add `GateType`, `GateTimeoutConfig`, `_timeout_error(gate, timeout_s)` to `gates/__init__.py`; add `tomllib`/`tomli` import; remove per-module `_timeout_error` duplicates.
3. Update `gates/python.py`: accept `config` in `run_python_suite` and `run_python_suite_on_dir`; resolve per-gate timeouts via `config.timeout_for()` or fallback.
4. Repeat for `gates/typescript.py`, `gates/go.py`, `gates/rust.py`.
5. Update `gates/__init__.py` `run_suite_for` / `run_suite_on_dir` to accept and forward `config`.
6. Update `server.py` `gate_run` (from `project_root`) and `gate_run_on_dir` (from target `directory`) to detect `.harness.toml` and pass loaded config.
7. Write integration tests for Python gate suite with injected `TimeoutExpired` and server.py handler config detection.
8. Verify all existing gate tests pass.
