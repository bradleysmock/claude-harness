# Requirements

**Ticket**: 0077
**Title**: Pluggable external gates (SARIF-in)

## Functional Requirements

1. Provide `gates/external.py`: a frozen `ExternalGateSpec` (`name`,
   `command: list[str]`, `scope: str | None`, `timeout_seconds: int`) and
   `run_external_gate(spec, directory: str) -> GateResult`, reusing the
   existing timeout-result pattern for a hang past `timeout_seconds`.
2. SARIF stdout maps to `GateError`s (`file`/`line`/`code`/`severity` from
   `physicalLocation`/`ruleId`/`level`); ingested paths are
   containment-checked against `directory` (mirrors `sarif_output.py`'s
   `_build_location`) — escaping/absolute -> `file=None`.
3. Invalid/absent SARIF, or `results` over `MAX_SARIF_RESULTS`, produces
   `TOOL_ERROR` (`passed=False`); non-zero exit alone is not sufficient.
4. `gates/config.py` parses `[external_gates]` fail-closed: `command` via
   `shlex.split`, validated against `_FORBIDDEN_ARG0_CHARS`/`_MAX_ARGS`
   (reused); each `scope` glob compiles via `gates/_scope.py`'s pattern
   compiler at parse time. A colliding `name` or malformed
   `command`/`scope` -> `ConfigError` -> `CONFIG_ERROR`.
5. `server.py` parses `[external_gates]` in its pre-loop `try/except
   ConfigError` (alongside `load_gate_overrides`), reusing
   `_config_error_payload`, then forwards the list to `run_suite_on_dir`
   as a new `external_gates` kwarg (forwarded only when set).
6. `run_suite_on_dir` gains an append step alongside coverage/dep-audit/
   sast: per gate, check `has_scope_match`, append the result unmodified
   — unlike those phases' own degrade-to-warning handling, a
   `TOOL_ERROR` here is never swallowed into a pass.
7. `external_gates.<name>.timeout` is its own field (default 60s), not
   composed into `GateTimeoutConfig`'s closed `GateType`-keyed fields.
8. A failing external gate reports run failure like a built-in gate,
   without short-circuiting sibling coverage/dep-audit/sast phases.
9. No `[external_gates]` block -> byte-identical behavior to today.

## Non-Functional Requirements

1. `command` never runs via a shell; a malformed entry fails closed.
2. Per-language redundancy for a scope-unrestricted gate is intentional
   (secrets/coverage/dep-audit/sast already re-run once per stack).

## Test Strategy

| Type        | Rationale                                              |
|-------------|-----------------------------------------------------------|
| Unit        | SARIF mapping incl. containment; oversize `results`/name/scope errors; hang -> timeout |
| Integration | `server.py` end-to-end `CONFIG_ERROR` shape; fixture -> `gate-findings.md`; scope-mismatch skipped; no block -> byte-identical |

## Acceptance Criteria

- A malformed entry (bad `command`/`scope`, or a colliding `name`) -> the
  same `CONFIG_ERROR` shape as a malformed `[gates]` override.
- A fixture SARIF script is scheduled and appears in `gate-findings.md`;
  an escaping path becomes `file=None`; a hang -> timeout; `TOOL_ERROR`
  never degrades to passing; no block -> identical.

## Open Questions

None — resolved in FR-5/FR-6/FR-8.
