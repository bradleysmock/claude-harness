---
description: "Run the test-quality assessment (Q1-Q6) and produce a two-axis scorecard that never averages fault detection against oracle validity."
argument-hint: "<unit path>"
---

# Quality audit — `$ARGUMENTS`

Assess the tests for `$ARGUMENTS` on two independent axes. Invoke the **verifier** for the judgement steps.

- **Q1 static smells** (V, no execution): no-assertion, weak assertion, tautological mocking, change-detector, happy-path-only, over-broad. Severity each. A floor, not a verdict.
- **Q2 mutation interpretation** (V over `mutation-diff.sh` output): kill-rate, coverage alongside, GAMING FLAG if coverage high but kill-rate low, a kill task per survivor, justified equivalents only.
- **Q3 oracle provenance** (V): every correctness assertion EXTERNAL / CHARACTERIZED / SELF-DERIVED; flag self-derived correctness claims.
- **Q4 refactor probe** (X): `scripts/refactor-probe.sh` renames privates and re-runs; newly-failing tests are implementation-coupled change-detectors. (Tier-1, warn-only until FP rate is zero.)
- **Q5 flakiness** (X): rerun ≥20× with randomized order/seed; report nondeterminism.

**Q6 scorecard** — two axes, do NOT average:
- FAULT DETECTION: kill-rate vs target, assertion density, smell counts, change-detector count, flakiness rate.
- ORACLE VALIDITY: % EXTERNAL vs SELF-DERIVED, open possibly-incorrect markers, unresolved human rulings.

Verdict: PASS only if fault detection meets thresholds AND oracle validity has zero self-derived correctness claims and zero open human items. A sharp test asserting the wrong thing is still wrong. Write to `.test-harness/scorecard-<unit>.md`.
