# Problem Statement

**Ticket**: 0083
**Title**: Clear repo-wide type_check debt so the coverage gate can run
**Date**: 2026-09-11

## Problem

`gates/__init__.py`'s `_append_coverage_gate` runs the coverage gate only
when every prior gate passed. `type_check` currently fails with 25 errors
across 11 files (confirmed growing, not static — 23 after ticket 0079, 27
mid-session, 25 now), so coverage never runs and its `gate-findings.json`
sidecar is never written — the exact condition `deliver-ticket.md` Step 1.6
treats as a fail-closed delivery blocker. Every recent ticket's delivery
(0078–0082) needed a manual sidecar workaround because of this.

## Impact

- The coverage-enforcement preflight (ticket 0011) has been structurally
  unable to run for the whole time this session has been delivering
  tickets — it isn't protecting anything right now.
- The debt keeps growing (new test files add new errors) rather than
  shrinking, so the gap widens with every ticket unless addressed directly.

## Success Criteria

- `mypy .` reports zero errors (informational `note:` lines about untyped
  function bodies are pre-existing and out of scope — they don't fail the
  gate).
- No suppression is added merely to silence an error whose underlying
  issue is real (a genuine type mismatch, a narrowing gap, an arity
  mismatch) — those are fixed at the source.
- A suppression is used only where the underlying condition is a real,
  permanent constraint (a third-party package with no available type
  stubs) — and is scoped narrowly (a `pyproject.toml` override for that
  one module), not a blanket ignore.
- `gates/__init__.py`'s `_append_coverage_gate` precondition is unchanged —
  this ticket clears the debt blocking it, not the gating logic itself.
- No test's asserted behavior changes — only type annotations, narrowing,
  and equivalent-behavior refactors of test helper functions.

## Out of Scope

- Whether coverage should be gated behind other gates passing at all
  (`_append_coverage_gate`'s own design) — a separate, larger question.
- The `security`/bandit findings mentioned in recent delivery reports —
  confirmed pre-existing and unrelated to `type_check`; not addressed here.
- Any change to `gates/coverage.py`'s own coverage-measurement logic.
