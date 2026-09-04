# Requirements

**Ticket**: 0077
**Title**: Pluggable external gates (SARIF-in)

## Functional Requirements

1. Provide `gates/external.py`: a frozen `ExternalGateSpec` (`name`,
   `command: list[str]`, `scope: str | None`, `timeout_seconds: int`) and
   `run_external_gate(spec, directory: str) -> GateResult`.
2. `run_external_gate` runs `spec.command` as an argv list (`shell=False`),
   reusing the existing timeout-result pattern for a hang past
   `timeout_seconds`.
3. SARIF stdout maps to `GateError`s (`file`/`line`/`code`/`severity` from
   `physicalLocation`/`ruleId`/`level`); every ingested path is
   containment-checked against `directory`, mirroring `sarif_output.py`'s
   `_build_location` — escaping/absolute -> `file=None`.
4. Invalid/absent SARIF, or `results` over `MAX_SARIF_RESULTS`, produces
   `TOOL_ERROR`; non-zero exit alone is never sufficient.
5. `gates/config.py` parses `[external_gates]` fail-closed: `command` via
   `shlex.split`, validated against `_FORBIDDEN_ARG0_CHARS`/`_MAX_ARGS`
   (reused). A `name` colliding with any built-in gate name or another
   `[external_gates]` entry -> `ConfigError` -> `CONFIG_ERROR`.
6. `run_suite_on_dir` gains an append step alongside coverage/dep-audit/
   sast: per gate, check `has_scope_match`, append the matched result —
   a sequential append, not a `GateSpec`/scheduler integration.
7. `external_gates.<name>.timeout` is its own field (default 60s), not
   composed into `GateTimeoutConfig`'s closed `GateType`-keyed fields.
8. An external gate's `passed` flag blocks like a built-in gate's — no
   advisory carve-out (deferred to the promotion-policy ticket).
9. No `[external_gates]` block produces byte-identical behavior to today.

## Non-Functional Requirements

1. `command` never runs via a shell; argv-list `subprocess.run` only. A
   malformed entry fails closed — never silently ignored or a crash.
2. Per-language redundancy for a scope-unrestricted gate is intentional
   (verified precedent: `server.py` calls `run_suite_on_dir` once per
   detected stack; secrets/coverage/dep-audit/sast already re-run inside).

## Test Strategy

| Type        | Rationale                                              |
|-------------|-----------------------------------------------------------|
| Unit        | SARIF mapping incl. path-containment; oversize `results`/name-collision -> error; hang past timeout -> timeout result |
| Integration | Fixture script -> `gate_run_on_dir` -> `gate-findings.md`; scope-mismatch skipped; no block -> byte-identical |

## Acceptance Criteria

- A fixture SARIF script, declared via `[external_gates]`, is scheduled
  and appears in `gate-findings.md`; a name colliding with a built-in
  gate -> `ConfigError`/`CONFIG_ERROR`.
- An escaping ingested path becomes `file=None`; a hang past timeout
  produces a timeout result, not an indefinite stall.
- Invalid/absent SARIF or a crash -> `TOOL_ERROR`; non-zero exit with
  valid SARIF is not; no block -> identical to today.

## Open Questions

None — resolved in FR-6/FR-7/FR-8.
