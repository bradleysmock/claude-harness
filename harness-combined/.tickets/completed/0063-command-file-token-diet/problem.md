# Problem Statement

**Ticket**: 0063
**Title**: Command-file token diet: move helper internals to docstrings; dedupe the critic-round persistence block
**Date**: 2026-07-20

## Problem

Command/flow files are loaded into every session that invokes them, so line count
is a recurring token cost. `commands/problem.md` restates in prose (~78 lines)
what `ticket_templates.py` / `ticket_deps.py` docstrings already say. The
"persist critic round to `critic-findings.md` + commit" instruction is
copy-pasted near-verbatim across 5 sites in `build-ticket.md` (2) and
`repair-escalation.md` (3: diagnosis persist, Phase 1 round persist, Phase 2
round persist) instead of being defined once.

## Impact

Every `/problem` run pays for duplicated Python-internals prose that drifts out
of sync when the helpers change. Every `/build`/repair-escalation run pays for
the persistence block up to 5x, and changing the convention needs 5 synced edits
instead of 1 — the drift risk `ticket-status.md:58-68` already avoids.

## Success Criteria

- `problem.md` Phase 1.5 and dependency-cycle-check sections reduced to pointers
  at `ticket_templates.py` / `ticket_deps.py` docstrings (per `ticket-status.md:58-68` pattern).
- The 5 critic-round persistence sites (`build-ticket.md` x2, `repair-escalation.md`
  x3) consolidated into `harness-reference.md`'s "Critic findings file" section,
  each site replaced by a short reference.
- No behavior change: same writes, same commits, same triggers — only docs dedup'd.
- Net line count of the 4 touched files drops (git diff --stat).

## Out of Scope

- Changing `ticket_templates.py` / `ticket_deps.py` behavior.
- Changing the persistence *format* itself, only its documentation.
- Token-diet audit of files beyond the 4 named above.
