---
description: "Phase 4 — refactor for testability under the frozen net, then write unit tests whose assertions cite an independent oracle. The only phase where assertions encode correctness."
argument-hint: "<unit path>"
---

# Phase 4 · Refactor + unit tests — `$ARGUMENTS`

Use the **generator** agent, working under the protection of the frozen characterization net.

1. Apply the enabling-point refactors from the seam map to make `$ARGUMENTS` testable (extract interfaces, inject clock/RNG/IO, break singletons). **The net must stay green throughout.** The hook blocks edits to the net itself; if a *source* edit turns the net red, STOP and escalate — behavior changed.
2. Write focused unit tests. For every assertion, cite its oracle claim id from `.test-harness/oracle-ledger.yaml`. Any assertion you cannot tie to a claim with `independence ≠ low` is UNSOURCED — re-source it or demote it to characterization; do not invent intended behavior from the implementation.
3. Resolve each `CHARACTERIZED: possibly-incorrect` marker: confirm intended (promote to a real assertion citing a claim) or file a bug.

**Gates:**
- X — the frozen net is still green.
- V — invoke the **verifier** for the oracle-provenance audit (Q3): every correctness assertion must be EXTERNAL, none SELF-DERIVED.
- H — human reviews the assertions and their oracles, not whether the suite passes.
