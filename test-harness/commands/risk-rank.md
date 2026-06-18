---
description: "Phase 2 — rank modules into risk waves using git churn, blast radius, complexity, and defect density. Never deprioritize high-risk-but-hard-to-test code."
argument-hint: "<path to analyze, default: repo root>"
---

# Phase 2 · Risk ranking

Use the **generator** agent with the git history of `$ARGUMENTS` as objective data — run the commands, do not estimate.

Per module compute: CHURN (`git log --numstat --since`), BLAST RADIUS (fan-in from the import graph), COMPLEXITY (a language analyzer), DEFECT SIGNAL (density of fix/bug/hotfix/revert commits), AMBIGUITY (from the seam map). Score ≈ normalize, weight `churn × blast_radius` up, complexity and defect signal as multipliers.

Write a ranked table to `.test-harness/risk-backlog.md` split into waves:
- Wave 1 = high-risk + low seam-cost (fast wins)
- Wave 2 = high-risk + high seam-cost (**refactor-then-test — never skip**)
- Wave 3 = the long tail

**Hard constraint:** do not deprioritize a module because its seam cost is high. High-risk + hard-to-test is the most important quadrant.

**Gate:** invoke the **verifier** to sanity-check the ranking — if a module everyone fears ranks low, the weighting or the git filter is wrong.
