---
description: "Oracle Stage 5 — turn weak/conflicted high-risk units into a batched human review packet (confirm/deny/correct), then record answers as authoritative claims."
argument-hint: "<unit path or subsystem>"
---

# Oracle · Elicitation packet — `$ARGUMENTS`

For the high-risk units under `$ARGUMENTS` with weak or conflicted oracle coverage, use the **generator** agent to produce a batched review packet — grouped by subsystem so the human stays in one context.

For each unit present: the weak/conflicted mined claims, the specific ambiguity, and 2–4 concrete proposed assertions phrased as **yes / no / correct-it**. Lead with the highest-risk units. Each decision must be answerable in under a minute without reading source.

Never ask "what should this do?" open-ended — review is far cheaper than authoring.

Write the packet to `.test-harness/elicitation-<subsystem>.md`. When the human answers, record each as an `ELICITED`, high-authority claim in `.test-harness/oracle-ledger.yaml`. These claims are reusable by every test touching that behavior, so the human cost amortizes.
