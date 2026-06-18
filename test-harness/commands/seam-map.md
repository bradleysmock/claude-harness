---
description: "Phase 0 — build a seam map for a module: classify dependencies, seam types, and refactor cost; gate with the verifier."
argument-hint: "<module path or glob>"
---

# Phase 0 · Seam map — `$ARGUMENTS`

Use the **generator** agent. Do NOT write tests. Produce a seam map for the unit(s) at `$ARGUMENTS`.

For each public unit:
1. List every collaborator and classify it: PURE, I/O / SIDE-EFFECTING (network, fs, db, clock, randomness, env, global state), or HIDDEN (static/singleton/ambient/implicit construction).
2. For each non-pure collaborator give the substitution mechanism and refactor cost: INJECTABLE (none), MODULE-MOCKABLE (low), or REQUIRES-REFACTOR (medium/high — describe the change).
3. Flag ENABLING POINTS: single refactors that unlock testing for many units at once.

Write the table to `.test-harness/seam-map.md` (columns: unit | collaborators | dependency class | seam type | substitution | refactor cost | enabling-point) and the language-idiomatic seam techniques available here.

**Gate:** invoke the **verifier** agent to challenge every "no-refactor" claim and confirm nothing side-effecting was misfiled as pure. Then ask the human to sign off before Phase 1.
