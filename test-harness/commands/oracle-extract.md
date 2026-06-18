---
description: "Oracle Stages 1-3 — extract normalized claims from harvested candidates, run the verifier independence gate, corroborate, and write the oracle ledger."
argument-hint: "<unit path>"
---

# Oracle · Extract + independence gate — `$ARGUMENTS`

Use the **generator** agent to convert the candidates in `.test-harness/oracle-candidates.yaml` for `$ARGUMENTS` into normalized claims:

```yaml
claim:
  id: oc-<unit>-NNNN
  unit: <unit>
  kind: precondition|postcondition|invariant|example|property|error
  statement: "<behavior in spec terms, NOT a paraphrase of the implementation>"
  oracle: { source: "<exact locator>", independence: high|medium|low, authority: high|medium|low }
  corroborated_by: [...]
  status: mined|conflicted|elicited|confirmed|unspecified
```

Detect and emit property-oracle claims (round-trip, idempotence, inverse, conservation, differential) from the unit's role — these need no known output. Mark anything you cannot tie to intent as `unspecified`; do not invent a claim to fill a gap.

**Independence gate (V):** invoke the **verifier** to re-grade independence adversarially and REJECT any claim whose expected behavior could only be known by reading the code under test (golden output, code-restating comments, impl-inferred values, characterization tests). High-authority / low-independence items are reclassified as characterization, not correctness.

**Corroborate / resolve:** promote claims confirmed by multiple independent sources; escalate conflicts (a type vs. a consumer, a docstring vs. a bug-fix) to the human — these usually reveal a latent bug or a stale doc.

Write surviving claims to `.test-harness/oracle-ledger.yaml`. A Phase 4 assertion is valid only if it cites a claim whose `independence` is not `low`.
