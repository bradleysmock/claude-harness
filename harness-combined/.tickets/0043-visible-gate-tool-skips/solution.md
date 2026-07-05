# Solution

**Ticket**: 0043
**Title**: Missing gate tools must be visible, never silent passes

## Approach

Extend the no-silent-failure philosophy to the skip path: add a small shared helper in
gates/__init__.py that builds a TOOL_SKIPPED warning GateError, use it at the two
silent-skip sites, thread warnings through to the findings renderer, and make the Stop
hook collect (rather than swallow) missing executables.

## Components

| Component | Responsibility |
|-----------|----------------|
| gates/__init__.py tool_skipped() | Canonical TOOL_SKIPPED GateError with install hint |
| gates/go.py, gates/rust.py | Replace silent-pass skip returns with warning-carrying passes |
| hooks/stop_full_gate.py | run_gate returns a skip marker; main() aggregates per stack |
| commands/gate.md | Skipped Tools section in gate-findings.md format |
| build-ticket.md Step 1 | One-line surfacing instruction referencing ticket 0022 |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Warning severity on a passing gate | Visibility without changing enforcement; models WARN tier |
| Shared helper in gates/__init__.py | One wording, one test, mirrors append_tool_error_if_silent |
| Hook stays exit 0 on skip-only turns | Skips are operator provisioning facts, not code defects |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | PATH-stripped fixtures for staticcheck and cargo-audit produce TOOL_SKIPPED, passed=True |
| FR-2 | Unit | Hook with missing pytest: skip line present, exit 0 clean / exit 2 when other failures exist |
| FR-3 | Unit | Docs grep + renderer test: Skipped Tools section emitted when warnings exist |
| FR-4 | Unit | Docs grep: build-ticket Step 1 contains the surfacing instruction |

## Tradeoffs

- **Chose warn-and-pass over fail-closed because**: failing every gate on missing
  optional tools would block work on minimal environments; visibility plus the 0022
  doctor is the right pressure.
- **Accepting risk of**: warning fatigue; the skip list is one line per stack, shown
  once per build.

## Risks

- Tests must manipulate PATH hermetically; use monkeypatched shutil.which rather than
  actual PATH edits.

## Implementation Order

1. gates/__init__.py helper + unit test.
2. go.py and rust.py skip sites.
3. stop_full_gate aggregation + exit-code tests.
4. gate.md renderer section and build-ticket Step 1 line; docs tests.
