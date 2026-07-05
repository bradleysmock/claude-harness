# Problem Statement

**Ticket**: 0052
**Title**: Align hook gates with MCP gates; record resolutions in failure memory
**Date**: 2026-07-05

## Problem

The Stop/PostToolUse hooks and the MCP gate suites enforce different things for the
same language. The Stop hook runs Go tests without the race detector while the MCP
gate uses -race; the per-write hook invokes a bare global eslint that most projects do
not have on PATH (their eslint lives in node_modules), so per-write JS linting almost
never fires — while the Stop hook correctly uses npx --no-install. Separately, failure
memory records only the error text: a retrieved "passed" narrative tells a future
repair that a similar failure was fixed, but not how, which halves its value.

## Impact

- Race conditions pass the turn-end hook and fail (or worse, intermittently pass) the
  MCP gate — inconsistent signals for the same code.
- JS/TS files get no per-write lint feedback in practice, delaying corrections to the
  slower Stop-hook loop.
- Repair loops re-derive fixes that past runs already found.

## Success Criteria

- Hook and MCP gate commands agree per language, with a drift-guard test.
- Per-write JS lint fires with project-local eslint installations.
- Passed-outcome memory records carry a resolution summary and retrieval shows it.

## Out of Scope

- New tools in either layer (tickets 0012, 0025, 0043).
- Memory schema redesign or pruning policy.
