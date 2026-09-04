# Solution

**Ticket**: 0077
**Title**: Pluggable external gates (SARIF-in)

## Approach

Add `gates/external.py`: `run_external_gate()` runs an operator-declared
argv command, parses SARIF stdout into `GateResult`/`GateError`
(mirroring `sarif_output.py`'s reverse mapping, incl. path containment).
`run_suite_on_dir` appends each parsed gate's result the same way it
already appends coverage/dep-audit/sast — sequentially, not through the
`GateSpec`/scheduler.

## Components

| Component | Responsibility |
|---|---|
| `gates/external.py` | `ExternalGateSpec`, `run_external_gate` (SARIF parse + path containment + timeout) |
| `gates/config.py` | Parses `[external_gates]`, reuses argv-hardening + rejects name collisions |
| `gates/__init__.py`'s `run_suite_on_dir` | Appends each matched external gate's result, alongside coverage/dep-audit/sast |
| `context/harness-reference.md`, `README.md` | Document the config surface and schema |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Sequential append in `run_suite_on_dir`, not `GateSpec`+scheduler | Each language module's `gate_defs` is a hand-written literal in its own file (`gates/python.py` etc.) — editing four files per feature is worse than the one shared append point `coverage`/`dep-audit`/`sast` already use |
| Path-containment check on ingested SARIF locations | `sarif_output.py`'s emission side already resolves against `worktree_root` and drops escaping paths; ingestion had no analogous check — an external tool's `physicalLocation` is untrusted output, not just its exit code |
| Name-collision rejection | `run_dir_gates_scheduled`'s gate-function dict is keyed by bare name; an external gate named `test` would silently replace the real `test` gate with no error |
| Reuse existing subprocess-timeout pattern; own timeout field (not `GateTimeoutConfig`-composed) | A hang must not stall a run indefinitely; that config's override fields are a closed `GateType` enum, invasive to extend |
| `MAX_SARIF_RESULTS` cap | An oversized `results` array from a misbehaving/hostile scanner must not balloon `gate-findings.md` |

## Decisions (resolves source doc's Checkpoint-1 questions + corrections)

- **Required-by-default**: yes, blocks like a built-in gate (promotion
  policy is a separate ticket's concern). **Scope DSL**: reuses
  `gates/_scope.py`'s comma-glob convention verbatim. **Timeout**: own
  field (Tech Choices).
- **Wiring-location correction**: an earlier draft cited a central
  "suite assembly" appending to every language's `gate_defs` — that list
  is actually a literal per language module. Corrected to a sequential
  append in `run_suite_on_dir`, matching coverage/dep-audit/sast exactly.
- **Redundant-dispatch precedent, verified**: `server.py` calls
  `run_suite_on_dir` once per detected stack; secrets/coverage/dep-audit/
  sast already re-run inside — read directly from the dispatch loop.
- **New under critique**: path containment, name-collision rejection, a
  `results`-size cap, and the timeout-kill reuse — none in the source doc.

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1/2      | Unit        | Valid SARIF maps correctly; a hang past `timeout_seconds` yields a timeout result |
| FR-3        | Unit        | An escaping/absolute ingested path becomes `file=None` |
| FR-4        | Unit        | Empty `runs` -> pass; malformed/absent stdout -> `TOOL_ERROR`; oversize `results` -> `TOOL_ERROR`; non-zero exit + valid SARIF -> not `TOOL_ERROR` |
| FR-5        | Unit        | Valid entry parses; bad `command`/oversize argv/forbidden `arg[0]`/name collision -> `ConfigError` |
| FR-6        | Integration | Fixture script in `_standards.md` appears in `gate-findings.md`; a scope-mismatched gate is actually skipped |
| FR-7/8/9    | Unit        | Timeout resolves independently; a failing external gate blocks; no block -> byte-identical |

## Tradeoffs / Risks

- **No richer scope DSL**: multi-language defaults need multiple entries
  (now name-collision-checked). Redundant per-language dispatch:
  accepted, matches verified existing behavior, not new.
- **New trust boundary named explicitly**: subprocess *stdout content* —
  from a tool possibly reacting to attacker-influenced repo content — is
  parsed into structured fields; mitigated by path containment (FR-3)
  and the size cap (FR-4).

## Implementation Order

1. Failing unit tests for SARIF mapping, path containment, timeout, and
   `TOOL_ERROR`/size-cap classification (FR-1-4); implement `run_external_gate`.
2. Failing unit tests for `[external_gates]` parsing incl. name-collision
   rejection (FR-5); implement in `gates/config.py`.
3. Failing integration test (incl. scope-skip) + wire the append step in
   `run_suite_on_dir` (FR-6, FR-7/8).
4. Regression test for no-block byte-identical behavior (FR-9); document
   the config schema in `context/harness-reference.md`/`README.md`.
