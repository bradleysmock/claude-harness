# Problem Statement

**Ticket**: 0070
**Title**: Status/stale ledger-sourced ticket discovery + nesting-aware worktree join
**Date**: 2026-07-19

## Problem

`ticket.py` resolves `repo` as the dir holding `.tickets/` — wrong once the
project is a monorepo subdirectory (`harness-combined/` here). It joins
worktree-relative paths (`repo/.worktrees/<slug>/.tickets/<slug>`) assuming the
worktree root *is* the project root; it isn't, since `git worktree add` checks
out the full tree one level deeper. Reproduced twice live this session: (1)
`claim()`'s stub lands as a stray top-level `.tickets/<slug>/` at the monorepo
root, disconnected from `harness-combined/.tickets/`; (2) `list_tickets()`'s
worktree join (feeds `list-json`, `/status`, `/stale`, `/ticket-list`) reads the
same wrong spot and falls back to stale data. Separately, `/status`/`/stale`
still enumerate via a raw `.tickets/*` scan on `main`; `claim()` writes nothing
there under the ledger model, so a new ticket is invisible, not just mis-stated.
`/ticket-list` fixed this identical gap (010d170); `/status`/`/stale` were
missed despite `/stale` declaring a "keep in sync" contract with `/status`.

## Impact

Any post-migration ticket is invisible to `/status`/`/stale` until delivered,
and its metadata lands outside the project tree, breaking `/build`/`/deliver`
for it. `/ticket-list` inherits the same read bug, currently masked.

## Success Criteria

- `ticket.py` computes each worktree's project-relative offset once (empty for a
  flat repo) and applies it to every worktree/ticket-dir path it builds.
- `claim()` writes the stub inside the worktree's real project dir; `list_tickets()`
  reads from that same corrected location.
- `/status`/`/stale` enumerate via `ticket.py list-json` unioned with the legacy
  scan, mirroring `/ticket-list`.

## Out of Scope

- Repairing already-misplaced legacy worktrees; `completed/`-only readers (velocity/sprint) — unaffected.
