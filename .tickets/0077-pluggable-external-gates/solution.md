# Solution

**Ticket**: 0077
**Title**: Pluggable external gates (SARIF-in)

## Approach

Add `gates/external.py`: `run_external_gate()` runs an operator-declared
argv command, parses SARIF stdout into `GateResult`/`GateError`
(mirroring `sarif_output.py`'s reverse mapping), and `to_gate_spec()`
adapts it into the existing `GateSpec` shape so it schedules and reports
exactly like a built-in gate — no scheduler change.

## Components

| Component | Responsibility |
|---|---|
| `gates/external.py` | `ExternalGateSpec`, `run_external_gate`, `to_gate_spec` |
| `gates/config.py` | Parses `[external_gates]`, reusing argv-hardening rules |
| `gates/__init__.py` (suite assembly) | Appends each parsed gate's `GateSpec` to every language's `gate_defs` |
| `context/harness-reference.md`, `README.md` | Document the config surface |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `directory: str`, not `Path` | Matches `run_dir_gates_scheduled`'s own signature — the source doc's `Path` was inconsistent with the codebase |
| TOOL_ERROR via `gates/__init__.py`'s pattern | Source doc cited `red_gate.py` (doesn't exist) and `finding_parser.py` (parses `gate-findings.md` prose, unrelated) |
| Timeout is its own field, not `GateTimeoutConfig`-composed | That config's override fields are a closed `GateType` enum (lint/typecheck/test/security) — extending it for arbitrary names is invasive |
| Append to every language's `gate_defs`, let `has_scope_match` filter | Simpler than pre-computing "which language does this scope belong to"; reuses the existing skip mechanism verbatim |
| Reuse `_FORBIDDEN_ARG0_CHARS`/`_MAX_ARGS` | Same hardening as today's `[gates]` command overrides — no parallel validation path |

## Decisions (resolves source doc's Checkpoint-1 questions + corrections)

- **Required-by-default**: yes — an external gate's `passed` flag blocks
  exactly like a built-in gate's; no advisory carve-out here (the
  promotion-policy ticket, not this one, will let it be marked optional).
- **Scope DSL**: reuses `gates/_scope.py`'s `GateSpec` pattern verbatim —
  no richer per-language DSL.
- **Timeout precedence**: its own simple field (see Tech Choices) —
  `GateTimeoutConfig` cannot cleanly extend to arbitrary names.
- **Citation corrections**: `red_gate.py` doesn't exist and
  `finding_parser.py` is unrelated — the real TOOL_ERROR precedent is
  `gates/__init__.py`'s `append_tool_error_if_silent`/`tool_skipped`.
  `run_external_gate`'s `directory` param is `str`, not `Path`.

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1/2      | Unit        | SARIF mapping: fields map correctly for a valid fixture document |
| FR-3        | Unit        | Empty `runs` -> pass; malformed JSON/absent stdout -> `TOOL_ERROR`; non-zero exit + valid SARIF -> not `TOOL_ERROR` |
| FR-4        | Unit        | `to_gate_spec` produces a `GateSpec` callable matching `(directory, config)` |
| FR-5        | Unit        | Valid entry parses; bad `command`/oversize argv/forbidden `arg[0]` -> `ConfigError` |
| FR-6        | Integration | Fixture SARIF script declared in `_standards.md`, picked up by `gate_run_on_dir`, appears in `gate-findings.md` |
| FR-7/8/9    | Unit        | Timeout resolves independently of `GateTimeoutConfig`; a failing external gate blocks like a built-in one; no block -> byte-identical |

## Tradeoffs / Risks

- **Redundant per-language dispatch for scope-unrestricted gates**:
  accepted, matching the existing `secrets`/`coverage` precedent rather
  than inventing new dedup logic.
- **No richer scope DSL**: an external tool needing per-language defaults
  must declare multiple `[external_gates]` entries — acceptable for v1.
- **Arbitrary subprocess execution from `_standards.md`**: mitigated by
  the same argv-list/`shell=False`/`_FORBIDDEN_ARG0_CHARS` hardening
  already trusted for command overrides; no new trust boundary crossed.

## Implementation Order

1. Failing unit tests for SARIF mapping + `TOOL_ERROR` classification
   (FR-1/2/3); implement `run_external_gate`.
2. Failing unit test for `to_gate_spec` (FR-4); implement.
3. Failing unit tests for `[external_gates]` parsing (FR-5); implement in
   `gates/config.py`, reusing existing validation.
4. Failing integration test + wire suite assembly to append parsed gates
   (FR-6, FR-7/8).
5. Regression test for no-block byte-identical behavior (FR-9); document
   in `context/harness-reference.md`/`README.md`.
