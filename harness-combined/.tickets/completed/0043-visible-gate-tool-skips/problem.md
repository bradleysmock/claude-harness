# Problem Statement

**Ticket**: 0043
**Title**: Missing gate tools must be visible, never silent passes
**Date**: 2026-07-05

## Problem

Several enforcement layers return success when their tool is not installed:
gates/go.py returns a passing staticcheck result with zero duration when staticcheck is
absent; gates/rust.py does the same for cargo-audit; and stop_full_gate.run_gate
returns (0, "") for any missing executable — on an unprovisioned machine the entire
Stop-hook gate layer is a silent no-op. The gate layer's own no-silent-failure
invariant (append_tool_error_if_silent) is not applied to the skip path.

## Impact

- Enforcement strength varies invisibly by machine; a lead cannot tell a clean pass
  from a vacuous one.
- Autonomous autopilot runs on under-provisioned environments deliver code that was
  never actually gated by the skipped tools.
- Debugging "why did this ship" requires knowing which tools existed at gate time —
  information currently recorded nowhere.

## Success Criteria

- Every skipped tool produces a visible, non-blocking warning in the gate result and in
  gate-findings.md.
- The Stop hook reports which tools it could not run instead of staying silent.
- The first gate run of a build surfaces the skipped-tool list to the lead.

## Out of Scope

- A standalone environment-doctor command (ticket 0022 owns that).
- Making skips blocking — warn-tier is deliberate; provisioning is an operator choice.
