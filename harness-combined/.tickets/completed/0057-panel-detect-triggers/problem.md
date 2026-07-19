# Problem Statement

**Ticket**: 0057
**Title**: Panel-detect script: deterministic trigger table in context/panels/triggers.md
**Date**: 2026-07-12

## Problem

Panel activation — deciding which expert panels the critic/critique/review flows
load — is a model-judgment step: the model reads a 30-row prose trigger table
embedded in `skills/critique/SKILL.md` and eyeballs globs, manifest presence,
dependency names, and content patterns against the files in scope. Per the
LLM/Python boundary rule (0053), these are exactness operations that belong in
Python: two runs can disagree on which panels activate.

## Impact

- Reviews of identical scopes can load different panel sets — missed panels mean
  missed findings (e.g. Cryptography or Identity silently not loaded).
- Every consumer (critic agent, /critique, /review, build flow) re-applies the
  table by judgment; there is no way to test activation behavior.
- The table is trapped inside one skill file; panel boilerplate in ~31 files
  points at it as "single source" while nothing enforces parity.

## Success Criteria

- Canonical trigger data extracted to `context/panels/triggers.md` in a
  machine-parseable form; every existing panel has an entry.
- A Python script deterministically maps (project root + in-scope files) →
  active panels, with judgment-only triggers surfaced as candidates for the
  model, never auto-activated or silently dropped.
- Fail-closed: missing/unparseable trigger data errors loudly (0053 rule).
- Consumers (`critique`/`review` SKILL.md, critic-brief, build flow, panel
  boilerplate) reference the new source; the old inline table is removed.
- Tests cover each trigger kind and table↔panel-file parity.

## Out of Scope

- Panel *content* changes; secondary-panel escalation; deference/priority rules.
- Design-artifact mode's scope inference (stays model judgment on the same data).
