# Solution

**Ticket**: 0077
**Title**: Pluggable external gates (SARIF-in)

## Approach

Add `gates/external.py`: `run_external_gate()` runs an operator-declared
argv command, parses SARIF stdout into `GateResult`/`GateError`
(mirroring `sarif_output.py`'s reverse mapping, incl. path containment).
`server.py` parses `[external_gates]` in its pre-loop `ConfigError`
handler (`_config_error_payload`) and forwards the list into
`run_suite_on_dir`, which appends each matched result the same way it
already appends coverage/dep-audit/sast — sequentially, not the scheduler.

## Components

| Component | Responsibility |
|---|---|
| `gates/external.py` | `ExternalGateSpec`, `run_external_gate` (SARIF parse + path containment + timeout) |
| `gates/config.py` | Argv hardening, scope-glob validation, name-collision rejection for `[external_gates]` |
| `server.py`'s pre-loop | Parses `[external_gates]` fail-closed (`_config_error_payload`), forwards to `run_suite_on_dir` |
| `run_suite_on_dir` | Appends each matched gate's result unmodified, alongside coverage/dep-audit/sast |
| `context/harness-reference.md`, `README.md` | Document the config surface and schema |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Sequential append in `run_suite_on_dir`, not `GateSpec`+scheduler | Each language's `gate_defs` is a hand-written literal per file — one shared append point beats editing four files |
| Parse in `server.py`'s pre-loop `ConfigError` handler, not inside `run_suite_on_dir` | Reuses `_config_error_payload` verbatim; parsing inside `run_suite_on_dir` would inherit its own degrade-to-warning exception handling — wrong for a config error |
| Path-containment check on ingested SARIF locations | `sarif_output.py`'s emission side already resolves against `worktree_root` and drops escaping paths; ingestion had none |
| Name-collision + scope-glob validation at parse time | A same-named gate produces an ambiguous `gate-findings.md` entry; an uncompiled glob silently degrades to "never runs" instead of erroring |
| Reuse subprocess-timeout pattern; own timeout field; `MAX_SARIF_RESULTS` cap | A hang must not stall a run; `GateTimeoutConfig`'s fields are a closed enum; an oversized `results` array must not balloon `gate-findings.md` |

## Decisions (resolves source doc's Checkpoint-1 questions + corrections)

- **Required-by-default**; **scope DSL** reuses `gates/_scope.py`'s
  comma-glob convention; **timeout** is its own field (Tech Choices).
- **Wiring/call-site corrections**: dropped `GateSpec`/`to_gate_spec`
  (sequential append in `run_suite_on_dir`, not the scheduler); parsing
  moved to `server.py`'s pre-loop `ConfigError` handler — the only site
  reusing `_config_error_payload`'s exact shape without the append
  phases' own fail-open exception handling.
- **Redundant-dispatch precedent, verified twice**: once per stack,
  matching secrets/coverage/dep-audit/sast's real behavior. **FR-8/9
  precision**: "blocks like a built-in gate" means the run reports
  failure, not a cross-phase short-circuit — matching how those phases
  already treat each other.

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1        | Unit        | Valid SARIF maps correctly; a hang yields a timeout result |
| FR-2        | Unit        | An escaping/absolute ingested path becomes `file=None` |
| FR-3        | Unit        | Empty `runs` -> pass; malformed/absent/oversize -> `TOOL_ERROR`; non-zero exit + valid SARIF -> not `TOOL_ERROR` |
| FR-4        | Unit        | Valid entry parses; bad `command`/argv/`scope` glob/name collision -> `ConfigError` |
| FR-5        | Integration | `server.py` end-to-end: malformed entry -> exact `CONFIG_ERROR` JSON, matching a malformed `[gates]` override |
| FR-6        | Integration | Fixture script appears in `gate-findings.md`; a scope-mismatched gate is skipped; its `TOOL_ERROR` is never degraded to a pass |
| FR-7/8/9    | Unit        | Timeout resolves independently; failure reports without cross-phase short-circuit; no block -> byte-identical |

## Tradeoffs / Risks

- **No richer scope DSL** (multi-language needs multiple, now
  collision-checked, entries); redundant per-language dispatch accepted.
- **New trust boundary named**: subprocess *stdout content* is parsed
  into structured fields; mitigated by containment (FR-2), size cap (FR-3).

## Implementation Order

1. Failing unit tests for SARIF mapping/containment/timeout/`TOOL_ERROR`
   size-cap (FR-1-3); implement `run_external_gate`.
2. Failing unit tests for `[external_gates]` parsing incl. scope-glob/
   name-collision (FR-4); implement in `gates/config.py`; failing
   integration test for `CONFIG_ERROR` shape + wire `server.py`'s
   pre-loop parse call (FR-5).
3. Failing integration test (incl. scope-skip) + wire the append step in
   `run_suite_on_dir` (FR-6-8); regression test for FR-9; document the
   schema in `context/harness-reference.md`.
