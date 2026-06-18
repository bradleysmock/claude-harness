---
description: "Phase 6 — the binding quality gate. Run diff-scoped mutation testing; loop verifier-triage → generator-kills until kill-rate target or all survivors are provably equivalent."
argument-hint: "<unit path>  [kill_target, default 0.75]  [max_iters, default 4]"
---

# Phase 6 · Mutation gate — `$ARGUMENTS`

The binding quality gate. Coverage proves a line executed; this proves a fault in it would be caught. Run the loop:

1. **X** — run `scripts/mutation-diff.sh $ARGUMENTS` (diff-scoped, new-code ratchet). Record score + survivors to `.test-harness/mutation-<unit>.json`.
2. If `kill_rate ≥ target` → DONE.
3. Else invoke the **verifier**: are the remaining survivors provably EQUIVALENT (no observable behavior distinguishes mutant from original across the whole input domain)? Justify each. If all are equivalent → DONE (documented). Tedium is not equivalence.
4. Else the verifier emits one concrete kill task per survivor; the **generator** writes the targeted tests. Re-run.
5. Stop at `max_iters`. Non-convergence → escalate to the human with the survivor report; do NOT fabricate kills to hit the number, and never weaken a test to raise the score.

Gaming check: if coverage is high but kill-rate is low, the suite executes the code without asserting on it — that is the signal this gate exists to catch.
