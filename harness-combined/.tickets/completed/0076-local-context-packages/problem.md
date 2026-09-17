# Problem Statement

**Ticket**: 0076
**Title**: Local context packages
**Date**: 2026-09-04

## Problem

`/problem` and `/build` hand the model static context files
(`context/harness-reference.md`, panels, rules) plus whatever the model
explores on its own. There is no ranked, task-relevant snippet pack
assembled up front — every ticket starts exploration from zero, costing
real turns to locate relevant files in a large or unfamiliar codebase.

## Impact

Anyone running `/problem` or `/build` on an unfamiliar area pays for
exploration turns that a cheap local search-and-rank pass could front-load.
Larger repos and less-explored corners of this codebase cost the most.

## Success Criteria

- A `context_fetch.py` module assembles a ranked snippet pack from local
  tools (ripgrep, optionally ast-grep) — no indexing daemon, no service.
- The pack is cached to disk per ticket, keyed by `(query text, HEAD)`, so
  an unchanged ticket/codebase state reuses the cached pack.
- `/problem` (from Phase 2 onward, once `problem.md` exists) and `/build`
  each inject the cached pack the same way `_standards.md`/`_learnings.md`
  are already loaded.
- Absent `ast-grep` degrades to ripgrep-only ranking, visibly, never a
  silent no-op and never a crash.

## Out of Scope

- A persistent code index (SCIP/Zoekt-equivalent) or any long-running
  process to keep an index warm.
- Replacing the model's own exploration — the pack is a head start.
- Recency-weighted ranking (`git log` churn) — a possible follow-up once
  plain keyword ranking is proven (see `solution.md § Decisions`).
