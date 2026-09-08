# Design: Pluggable external gates (SARIF-in)

**Date:** 2026-09-03
**Status:** Proposed (not yet ticketed)
**Author:** Bradley + Claude
**Origin:** Comparison against agentic-dev-platform's `gate_engine.yaml`, which adds
any SARIF-emitting external tool as a first-class gate declaratively, with no code
change per tool.

## Problem

`gates/config.py` lets `_standards.md` override the *command* for a fixed set of
gate slots per language (`lint`, `type_check`, `test`, `security` — see
`_VALID_GATES`). Adding a genuinely new tool — Snyk, SonarQube, a custom checker —
still means writing a new `gates/*.py` module and wiring it into the suite runner.
`sarif_output.py` already emits the harness's own findings as SARIF for external
consumption; there is no equivalent path for *ingesting* SARIF from a third-party
tool as a gate.

## Goal

Let the `[gates]` block declare additional gates by name that run an arbitrary
subprocess whose stdout is SARIF 2.1.0, parsed into `GateResult`/`GateError` by a
generic adapter, and scheduled and reported exactly like a built-in gate — no new
`gates/*.py` module required to add a SARIF-emitting tool.

## Non-goals

- Ingesting non-SARIF tool output (a second `output_format` can follow later, once
  one shape is proven).
- Auto-installing or discovering third-party scanners; the operator names an
  already-installed binary, same as today's `[gates]` command overrides.
- Changing whether an external gate blocks promotion — that is
  [[2026-09-03-data-driven-promotion-policy-design]]'s concern, not this one's.

## Architecture

### 1. `gates/external.py` (new)

```python
@dataclass(frozen=True)
class ExternalGateSpec:
    name: str
    command: list[str]      # argv, never shell=True
    scope: str | None       # file-glob patterns, reuses gates/_scope.py
    timeout_seconds: int

def run_external_gate(spec: ExternalGateSpec, directory: Path) -> GateResult: ...
```

Runs `spec.command` as a subprocess against `directory`, captures stdout, and
parses it as SARIF JSON — the mirror image of `sarif_output.py`'s
`GateResult → SARIF` mapping. Each SARIF `result` becomes a `GateError`: `file`/
`line` from `physicalLocation`, `code` from `ruleId`, `severity` from `level`.
Invalid or absent SARIF on stdout (non-zero exit is not itself sufficient — many
scanners exit non-zero *because* they found something) becomes a `TOOL_ERROR`
`GateResult`, the same failure class `red_gate.py`/`finding_parser.py` already
use for a broken tool.

### 2. Config surface (`gates/config.py`)

A new fenced sub-block, parsed with the same fail-closed discipline as today's
`[gates]` overrides (malformed entry → `ConfigError`, surfaced as a
`CONFIG_ERROR` finding, never silently skipped):

```
```gates
[external_gates]
snyk = { command = "snyk test --sarif", scope = "*.py,*.ts", timeout = 120 }
```
```

`command` is `shlex.split` and hardened against the existing `_FORBIDDEN_ARG0_CHARS`
/ `_MAX_ARGS` rules — reused, not reimplemented.

### 3. Wiring

`run_dir_gates_scheduled` (`gates/__init__.py`) already runs a dependency-ordered
list of gate callables through a `ThreadPoolExecutor`. Parsed external gates are
appended to whichever language suite(s) match their `scope` and run through that
existing scheduler untouched — no scheduler change.

### 4. Reporting

An external `GateResult` renders in `gate-findings.md` exactly like a built-in one
(`## <language> / <gate-name>`), since `commands/gate.md`'s Step 5 renderer only
ever sees `GateResult` objects, not gate identities.

## Files to change

- `gates/external.py` — new.
- `gates/config.py` — parse the `[external_gates]` sub-block.
- `gates/__init__.py` (or the per-language suite runners) — append parsed
  external gates to the scheduled gate list.
- `context/harness-reference.md`, `README.md` — document the config surface.
- `tests/test_external_gates.py` — new.

## Verification

1. **SARIF mapping**: valid SARIF stdout → correct `GateError` list; empty
   `runs` → passing `GateResult`; malformed JSON → `TOOL_ERROR`.
2. **Config parsing**: a valid `[external_gates]` entry parses; a malformed one
   (bad `command`, oversize argv, forbidden `arg[0]`) raises `ConfigError`.
3. **Integration**: a fixture script that prints canned SARIF, declared in
   `_standards.md`, is picked up by `gate_run_on_dir` and appears in
   `gate-findings.md`.
4. **Regression**: a project with no `[external_gates]` block behaves
   byte-identical to today (additive-only, same principle as
   `ticket_templates.py`'s custom sections).

## Open decisions for Checkpoint 1

1. Is an external gate `required` (blocks promotion) by default, or advisory
   unless the operator opts it in? Interacts directly with the promotion-policy
   design.
2. Does `scope` reuse `gates/_scope.py`'s existing `GateSpec` pattern verbatim, or
   does an arbitrary external tool need a richer scope DSL (e.g. per-language
   defaults)?
3. Timeout precedence: does `external_gates.<name>.timeout` compose with
   `GateTimeoutConfig`'s existing override → global → default resolution, or is
   it a separate, simpler knob?
