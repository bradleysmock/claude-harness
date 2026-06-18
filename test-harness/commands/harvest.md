---
description: "Oracle Stage 0 — harvest candidate oracle sources for a unit (git/bug history, schemas, call sites, in-code contracts, standards). Deterministic gather; no judgement."
argument-hint: "<unit path>"
---

# Oracle · Harvest candidates — `$ARGUMENTS`

Gather candidate oracle sources for the unit(s) at `$ARGUMENTS`. This step only **gathers and locates** — it never grades independence or writes claims.

Run the deterministic harvesters:
- `scripts/harvest-bugfix.sh $ARGUMENTS` — closed bug reports + fix commits (high-independence regression oracles) and reverts (negative oracles).
- Scan for: schemas/IDL (OpenAPI, protobuf, GraphQL, JSON Schema, DB CHECK/NOT NULL constraints), consumer call sites (from seam-map fan-in: fields accessed, non-null assumptions, catch blocks), in-code contracts (`require`/`assert`/validation annotations + throw conditions), doc-comment tags (`@throws…when`, `@param`, `@returns`), referenced standards (and their published test vectors), and any reference/legacy twin implementation.

Anchor every candidate to its unit by line-span intersection, and record an exact, re-fetchable locator (sha / file:line / issue URL / schema path). Append candidates to `.test-harness/oracle-candidates.yaml` with `suggested_independence` / `suggested_authority` defaults from source type.

Do not extract claims yet — that is `/test-harness:oracle-extract`.
