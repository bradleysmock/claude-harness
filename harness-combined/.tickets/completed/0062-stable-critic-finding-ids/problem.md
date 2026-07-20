# Problem Statement

**Ticket**: 0062
**Title**: Stable critic finding IDs
**Date**: 2026-07-19

## Problem

The post-build repair loop (`build-ticket.md` Step 7a) re-spawns the critic
fresh each round with no memory of prior findings; its only cross-round check
is aggregate — "does the new report have any BLOCKER/MAJOR?" There is no
per-finding identity, so the loop can't tell which findings were fixed,
persisted, or newly introduced. `critic-findings.md` is append-only prose,
not keyed data.

A stable key (`file:line:severity:code`) already exists as `critic_hash()` in
`gates/comment_deduplicator.py` (ticket 0031) — `code` is already populated
with the finding's Panel/Dimension label (`_finalize` in
`critic_finding_parser.py`). But it's private to PR-comment dedup, not
exposed for reconciliation.

## Impact

Repair progress is opaque ("3 findings before, 2 after" says nothing about
which). Ticket 0067 needs a "prior BLOCKER/MAJOR list" to diff against, which
doesn't exist as structured data today.

## Success Criteria

- The existing `(file, line, severity, code)` key is shared between
  PR-comment dedup and a new repair-loop reconciler — one implementation.
- A reconciliation function classifies findings as fixed / persisted / new.
- Step 7a surfaces the reconciliation summary every round, including round 1,
  and persists keyed findings so later rounds/tickets can consume them.

## Out of Scope

- Changing what `code` contains or the severity-tier source (ticket 0058).
- Implementing ticket 0067's diff-scoped review behavior — this ticket only
  produces the reconciliation primitive 0067 will consume.
