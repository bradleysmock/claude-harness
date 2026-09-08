# Problem Statement

**Ticket**: 0077
**Title**: Pluggable external gates (SARIF-in)
**Date**: 2026-09-04

## Problem

`gates/config.py` only lets `_standards.md` override the *command* for a
fixed set of gate slots per language (`lint`, `type_check`, `test`,
`security`). Adding a genuinely new tool — Snyk, SonarQube, a custom
checker — still means writing a new `gates/*.py` module by hand.
`sarif_output.py` emits the harness's own findings as SARIF; there is no
equivalent path for *ingesting* SARIF from a third-party tool as a gate.

## Impact

Anyone wanting a third-party scanner enforced as a gate must write and
maintain a bespoke module, even when the tool speaks a standard format.

## Success Criteria

- `_standards.md`'s `[gates]` block can declare an `[external_gates]`
  entry naming an arbitrary subprocess whose stdout is SARIF 2.1.0,
  parsed into `GateResult`/`GateError` and scheduled/reported exactly
  like a built-in gate — no new `gates/*.py` module required per tool.
- A malformed `[external_gates]` entry fails closed (`CONFIG_ERROR`),
  never silently skipped.
- Invalid/absent SARIF on stdout becomes a `TOOL_ERROR` result — non-zero
  exit alone is not sufficient, since many scanners exit non-zero on
  real findings.
- No `[external_gates]` block behaves byte-identical to today.

## Out of Scope

- Ingesting non-SARIF tool output (a future `output_format` extension).
- Auto-installing/discovering scanners — the operator names an
  already-installed binary, same as today's command overrides.
- Whether an external gate blocks promotion — the promotion-policy
  ticket's concern, not this one's.
