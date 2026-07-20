# Problem Statement

**Ticket**: 0058
**Title**: Single-source severity tiers: define BLOCKER/MAJOR/MINOR/OBS in harness-reference only
**Date**: 2026-07-12

## Problem

The 4-tier severity taxonomy is fully defined in three places with already-drifted
wording: `context/harness-reference.md:336-339` (BLOCKER "Blocks merge"),
`context/critic-brief.md:77-80` ("Blocks the next checkpoint"), and
`skills/critique/SKILL.md:171-175` ("Must be resolved before shipping").
Nothing stops a fourth copy appearing or the three diverging further.

## Impact

- Critic, review, and critique agents load different definitions depending on
  entry path — the same finding can be tiered or actioned inconsistently.
- Editors fixing one copy silently leave the others stale (drift is already real).
- `skills/review/SKILL.md:53` shows the intended pattern (pointer to
  harness-reference) — the other two files predate it.

## Success Criteria

- Exactly one full tier-definition block exists, in `context/harness-reference.md`,
  worded to fit all consumers (design review, code review, diff critique).
- `context/critic-brief.md` and `skills/critique/SKILL.md` replace their definition
  blocks with a pointer to the canonical block, keeping any mode-specific guidance.
- A drift test fails when any runtime-loaded prose file outside harness-reference
  re-defines the taxonomy (`docs/` and `.tickets/` are historical records, excluded)
  or the canonical block loses a tier; it pins the names to
  `critic_finding_parser._SEVERITIES` and fails closed on scan-root misses.

## Out of Scope

- Panel files' severity *assignments* (e.g. cryptography.md "Severity convention")
  — they apply tiers to hazards, they do not define the taxonomy.
- Code enums (`gates/sast_models.py`, `gates/dep_audit.py`) — gate-internal
  severities, not the critic taxonomy.
- Changing tier semantics or the must-fix policy split (BLOCKER+MAJOR vs MINOR/OBS).
