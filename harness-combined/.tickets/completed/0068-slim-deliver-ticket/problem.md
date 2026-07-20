# Problem Statement

**Ticket**: 0068
**Title**: Slim deliver-ticket.md: move merge/archive/learnings mechanics behind ticket.py
**Date**: 2026-07-20

## Problem

`deliver-ticket.md` Step 4 hand-spells the git sequence
`ticket.py::deliver_squash()` already implements and unit-tests, but that
function has no CLI subcommand and is never called from the flow. Step 5's
learnings capture (parse-gate-findings.md, candidate-learnings-flow.md)
expresses parsing/sanitization/dedup — an injection-relevant trust boundary —
as prose the model executes each delivery. `/problem` Phase 1 already moved
claim mechanics behind `ticket.py claim --push`; delivery never got the same
treatment, and `/harvest-learnings` shares this sanitize/dedup/append logic.

## Impact

- Drift risk: markdown and `deliver_squash()` can diverge silently (no drift
  test, unlike the hook/gate parity table).
- Attacker-influenceable text is sanitized via LLM prose at two call sites
  (`/deliver`, `/harvest-learnings`), violating CLAUDE.md's LLM/Python boundary.
- `deliver_squash()` bundles commit+push+cleanup, but Step 4b's smoke test
  must gate between them.

## Success Criteria

- `ticket.py` splits squash+archive+commit from publish+cleanup as CLI
  subcommands; Step 4/4c call them, not inline git.
- Learnings sanitize/dedup/append move into tested Python behind a thin CLI,
  used by **both** `/deliver` and `/harvest-learnings`.
- Delivery/harvest behavior unchanged; tests updated to the new CLI shape.

## Out of Scope

- `/harvest-learnings`'s BM25 memory.db retrieval stays in prose — only its
  sanitize/dedup/append calls move.
- Step 4b smoke test, 2b rebase guard, 3.5 PR creation, 7 in-flight rebase,
  severity/cap/dedup semantics changes.
