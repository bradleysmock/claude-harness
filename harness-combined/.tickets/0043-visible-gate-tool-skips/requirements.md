# Requirements

**Ticket**: 0043
**Title**: Missing gate tools must be visible, never silent passes

## Functional Requirements

1. Gate suites must emit a warning-severity TOOL_SKIPPED entry (tool name, gate name,
   one-line install hint) in the GateResult when an optional tool is absent, replacing
   the current passed-with-zero-duration results in gates/go.py (staticcheck) and
   gates/rust.py (cargo-audit); the gate still counts as passed.
2. stop_full_gate.run_gate must accumulate missing executables and include a
   "skipped tools" line per stack in its stderr output; when failures also exist the
   line joins the blocking report, and when the turn is otherwise clean the hook must
   still exit 0 (non-blocking) — the skip list is informational.
3. The gate-findings.md renderer (commands/gate.md format) must include a Skipped Tools
   section whenever any TOOL_SKIPPED entry is present.
4. build-ticket.md Step 1 must instruct the model to surface the skipped-tool list from
   the first gate run of the build in one line to the lead, citing ticket 0022's doctor
   as the remediation path.

## Non-Functional Requirements

1. TOOL_SKIPPED entries must be distinguishable from TOOL_ERROR (tool present but
   crashed) in code and docs.
2. No change to pass/fail semantics of any existing gate.

## Test Strategy

| Type | Rationale                                                      |
|------|------------------------------------------------------------------|
| Unit | Absent-tool fixtures produce TOOL_SKIPPED warnings, passed=True |
| Unit | stop_full_gate output contains skip lines and correct exit codes |
| Unit | Docs greps for findings-section and build Step 1 wiring          |

## Acceptance Criteria

- With staticcheck removed from PATH, the Go suite passes and its result contains one
  TOOL_SKIPPED warning naming staticcheck.
- With pytest removed, stop_full_gate output names pytest as skipped and exits 0 when
  nothing else fails.
- gate-findings.md for a run with skips contains a Skipped Tools section.

## Open Questions

- None.
