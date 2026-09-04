# Requirements

**Ticket**: 0077
**Title**: Pluggable external gates (SARIF-in)

## Functional Requirements

1. Provide `gates/external.py`: a frozen `ExternalGateSpec` (`name`,
   `command: list[str]`, `scope: str | None`, `timeout_seconds: int`) and
   `run_external_gate(spec, directory: str) -> GateResult` (`str`, not
   `Path` — matches `run_dir_gates_scheduled`'s own signature).
2. `run_external_gate` runs `spec.command` as an argv list (`shell=False`),
   parses stdout as SARIF, mapping each `result` to a `GateError`
   (`file`/`line`/`code`/`severity` from `physicalLocation`/`ruleId`/
   `level`) — the inverse of `sarif_output.py`'s mapping.
3. Invalid/absent SARIF on stdout must produce `TOOL_ERROR` (matching
   `gates/__init__.py`'s `append_tool_error_if_silent`/`tool_skipped`
   pattern — not `red_gate.py`, which doesn't exist, nor
   `finding_parser.py`, an unrelated parser). Non-zero exit alone is
   never sufficient — scanners often exit non-zero on real findings.
4. `to_gate_spec(spec) -> GateSpec` adapts `run_external_gate` into the
   `(directory, config) -> GateResult` shape `GateSpec.fn` expects
   (`config` ignored, FR-7); `scope` parses via `gates/_scope.py`'s glob.
5. `gates/config.py` parses `[external_gates]` fail-closed: `command` via
   `shlex.split`, validated against `_FORBIDDEN_ARG0_CHARS`/`_MAX_ARGS`
   (reused); malformed -> `ConfigError` -> `CONFIG_ERROR`.
6. Each parsed gate is appended, via `to_gate_spec`, to every language's
   `gate_defs`; `has_scope_match` decides per-language inclusion.
7. `external_gates.<name>.timeout` is its own field (default 60s),
   resolved independently — not composed into `GateTimeoutConfig`, whose
   override fields are keyed by a closed `GateType` enum.
8. An external gate's `passed` flag blocks like a built-in gate's — no
   advisory carve-out (deferred to the promotion-policy ticket).
9. No `[external_gates]` block produces byte-identical behavior to today.

## Non-Functional Requirements

1. `command` is never run via a shell; argv-list `subprocess.run` only. A
   malformed entry fails closed — never silently ignored or a crash.
2. A scope-unrestricted gate may run once per detected language
   (redundant, consistent with the `secrets`/`coverage` precedent).

## Test Strategy

| Type        | Rationale                                              |
|-------------|-----------------------------------------------------------|
| Unit        | SARIF mapping (valid/empty/malformed -> `TOOL_ERROR`); config parsing (valid/malformed -> `ConfigError`) |
| Integration | Fixture script in `_standards.md` -> `gate_run_on_dir` -> `gate-findings.md`; no block -> byte-identical |

## Acceptance Criteria

- A fixture SARIF script, declared via `[external_gates]`, is scheduled,
  parsed, and appears in `gate-findings.md`; a malformed entry ->
  `ConfigError`/`CONFIG_ERROR`, never silent.
- Invalid/absent SARIF or a crash -> `TOOL_ERROR`; non-zero exit with
  valid SARIF is not `TOOL_ERROR`; no block -> identical to today.

## Open Questions

None — resolved in FR-6/FR-7/FR-8.
