---
description: "Drive one module end-to-end through the full pipeline (P0 → P6), pausing at the two human gates. Use this for the walking-skeleton pilot."
argument-hint: "<module path>  [kill_target]"
---

# Run module end-to-end — `$ARGUMENTS`

Execute the pipeline for `$ARGUMENTS` in order, honoring every gate. This is the manual driver for a single-module pilot — no durable orchestrator required.

1. `/test-harness:seam-map $ARGUMENTS` → **pause for human seam sign-off.**
2. `/test-harness:harvest $ARGUMENTS` then `/test-harness:oracle-extract $ARGUMENTS`.
3. If oracle coverage is weak for high-risk units: `/test-harness:elicit $ARGUMENTS` → **pause for human answers.**
4. `/test-harness:characterize $ARGUMENTS` (freezes the net).
5. `/test-harness:unit-tests $ARGUMENTS` → **pause for human oracle review (Q3).**
6. `/test-harness:contract-tests $ARGUMENTS`.
7. `/test-harness:mutation-gate $ARGUMENTS` (loop to target or escalate).
8. `/test-harness:quality-audit $ARGUMENTS`.

Record what each step costs (tokens, time, your review minutes), the oracle yield (fraction of assertions with an independent oracle), and the verifier catch-rate — this run is the calibration dataset, not just tested code. Stop and report if any hard gate halts (net red, unsourceable assertion, mutation non-convergence).
