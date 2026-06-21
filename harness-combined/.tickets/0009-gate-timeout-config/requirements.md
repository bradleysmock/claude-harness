# Requirements

**Ticket**: 0009
**Title**: Gate timeout configuration

## Functional Requirements

1. The system must load a `GateTimeoutConfig` from `.harness.toml` at the project root (or the directory passed to `gate_run_on_dir`) when the file exists; fall back gracefully when it does not exist.
2. `GateTimeoutConfig` must support a `default_timeout_seconds` integer key and per-gate-type overrides: `lint_timeout_seconds`, `typecheck_timeout_seconds`, `test_timeout_seconds`, `security_timeout_seconds`.
3. Per-gate-type timeout must take precedence over the global default; the global default must take precedence over the current hardcoded values.
4. When a gate process exceeds its configured timeout, it must terminate and return a failed `GateResult` with `code="TIMEOUT"` and a message that includes the gate name and the configured timeout value (e.g., `"lint gate timed out after 30 s"`).
5. When no `.harness.toml` exists, all gate behavior must be identical to today — no regression.
6. `GateTimeoutConfig` must be loadable from `gates/__init__.py` and passed down into `run_suite_for` and `run_suite_on_dir` via an optional parameter with a `None` default (no-change to callers that omit it).
7. The `gate_run` (text-mode) handler in `server.py` must detect `.harness.toml` in `project_root` and pass the loaded config to the suite; `gate_run_on_dir` must detect it in the target directory.

## Non-Functional Requirements

1. Config loading must complete in < 20 ms (TOML parse of a small file; no I/O retry loops).
2. Passing `None` for `GateTimeoutConfig` must be a zero-overhead path — no conditional branches in the hot subprocess call.

## Tech Stack

N/A — extending existing Python codebase; adding `tomllib` (stdlib since 3.11) for `.harness.toml` parsing.

## Test Strategy

| Type        | Rationale                                                                 |
|-------------|---------------------------------------------------------------------------|
| Unit        | `GateTimeoutConfig` load/parse: valid file, missing file, malformed TOML, per-key precedence, zero/negative values, unknown keys, float truncation |
| Unit        | `_timeout_error(gate, timeout_s)` message includes gate name and timeout value |
| Unit        | `server.py` handlers load config from correct directory per mode |
| Integration | Python gate suite: mock `subprocess.run` to raise `TimeoutExpired`; assert `GateResult` has correct message and `code="TIMEOUT"` |

## Acceptance Criteria

- A `.harness.toml` with `test_timeout_seconds = 30` causes the test gate to pass `timeout=30` to `subprocess.run`.
- A `.harness.toml` with `default_timeout_seconds = 45` causes lint and typecheck gates to pass `timeout=45` when no per-gate override is set.
- A missing `.harness.toml` produces no error and uses existing hardcoded defaults.
- A malformed `.harness.toml` raises a `ValueError` wrapping `tomllib.TOMLDecodeError`, with the filename included in the message.
- A `.harness.toml` with a zero or negative timeout value (e.g., `test_timeout_seconds = 0`) raises `ValueError` at load time.
- A `.harness.toml` with unknown keys (e.g., `typo_timeout_seconds = 10`) is silently ignored.
- A `.harness.toml` with a float value (e.g., `test_timeout_seconds = 30.5`) is accepted and truncated to `int`.
- The timeout error message reads: `"<gate> gate timed out after <N> s"`.
- All existing gate tests continue to pass.

## Open Questions

- Should `.harness.toml` also be checked in `_standards.md` as a fenced block (as done in ticket 0004 for `stale_threshold_days`)? Current decision: use `.harness.toml` only (dedicated machine-readable file, not embedded in Markdown). Revisit if the lead prefers `_standards.md`.
