# Design: Failure-memory forward-injection (proactive gotchas)

**Date:** 2026-07-19
**Status:** Proposed (Checkpoint 1 pending)
**Author:** Bradley + Claude
**Basis:** current `main` (harness-combined v1.10.0), reviewed against the shipped
`resolution` column from ticket 0052.

## Problem

Failure memory (`memory.py`, `.harness/memory.db`) is persistent and cross-spec,
but it is **consumed reactively only**. `memory(action="retrieve", ...)` fires
exclusively inside the repair loop, *after* a gate has already failed
(`build-spec.md`, `build-ticket.md` Step 4e/7a). A failure mode hit and resolved
in spec A never shapes the **first** generation attempt of spec B in the same
area — the model re-derives the mistake, fails the gate, and only then is shown
the past failure. The corpus exists; the forward arrow does not.

Ticket 0052 sharpened the corpus (each resolved record now stores a one-line
`resolution` — *how* it was fixed, not just that it failed), which makes forward
injection more valuable than at first review: a proactive gotcha can now carry
the fix, not merely the symptom. But 0052 changed only what `retrieve` returns
during repair; it did not add a forward path.

## Goal

Feed the persisted corpus **forward** into the generation step, so the first
attempt pre-empts known, area-local failure modes and their known fixes — without
touching the reactive repair path or the gate engine.

## Non-goals

- Replacing the reactive `retrieve` path — purely additive.
- Embeddings / semantic retrieval — stay BM25-only, consistent with `memory.py`.
- Auto-editing `.tickets/_learnings.md` (lead-curated by contract). Injection
  targets the ephemeral generation prompt, not curated files.
- Cross-project memory. Stays per-project.

## What already exists on main (and how it helps)

- `failure_records` now carries `outcome`, `attempt`, and **`resolution`** (0052).
- `_migrate_resolution_column` (`memory.py:176`) is a **proven idempotent
  `ALTER TABLE … ADD COLUMN` with a PRAGMA guard and duplicate-column race
  swallow**. This is exactly the migration shape a new column needs — generalize
  it to `_migrate_column(conn, name)` and reuse for `target_file`.

What is still missing: no `target_file` on records, no domain-keyed retrieval, no
injection into generation.

## Why the corpus can't be queried at generation time today

`retrieve_similar(errors_text, gate)` keys on **error text**, which does not exist
yet when generation starts. To retrieve before the first gate we must key on the
spec's *domain signals* — `target_file` and `description` — but records store no
`target_file`, so "what failed before in this area" is unanswerable.

## Approach (Approach A — domain-keyed `gotchas` action)

One additive column (via the proven migration), one new memory action, two
flow-step edits.

### 1. Schema: record the target area

Generalize `_migrate_resolution_column` → `_migrate_column(conn, "target_file")`
and call it for both `resolution` (unchanged) and the new `target_file` in
`_init_db`. `_SCHEMA`'s `CREATE TABLE` names `target_file` for fresh DBs. This
reuses 0052's exact race-safe pattern rather than inventing a new one.

`record(...)` and `memory(action="record", ...)` gain an optional `target_file`
(default `None`), threaded from the `spec.target_file` already in hand at record
time. Existing call sites that omit it keep working (column is NULL).

### 2. New retrieval mode: `gotchas`

`memory(action="gotchas", target_file=, description=, language=, project_root=,
limit=3)` returns a compact "Known gotchas in this area" block, or empty string
when nothing is relevant.

- **Filter:** `outcome = 'passed'` only — a *resolved* failure is actionable and,
  post-0052, carries a `resolution` to inject. (`escalated` records are noisier /
  possibly environmental; off by default, a later toggle.)
- **Filter:** `gate` restricted to the gates for `language` (reuse the
  language→gate-name map the suite already defines).
- **Rank:** area proximity first (exact `target_file`, then same directory), then
  BM25 over `description` tokens as tiebreaker.
- **Cap:** `limit` (default 3), each narrative truncated like `retrieve_similar`.

Format (short — it rides in the generation prompt, and now surfaces the fix):

```
Known gotchas in this area (resolved past failures):
  ⚠ <gate> previously failed on <target_file or dir>: <error excerpt>
    → fixed by: <resolution>   (pre-empt it)
```

### 3. Inject at generation, in both build flows

- `build-spec.md` — before the **Generate** step, call `memory(action="gotchas",
  target_file=spec.target_file, description=spec.description, language=language,
  project_root=project_root)`; if non-empty, prepend as a hard "avoid these known
  failure modes" note.
- `build-ticket.md` — same, in **Step 4c**, per spec.

Reactive `retrieve` calls are untouched. A failure now informs both its own repair
loop (reactive) and future generations in the same area (proactive).

### 4. Thread `target_file` into existing `record` calls

The on-pass / on-exhaustion `memory(action="record", ...)` calls in both flows add
`target_file=spec.target_file` (alongside the `resolution` 0052 already threads).
Without this, new records are retrievable only by the legacy error-keyed path, not
by `gotchas`.

## Alternatives rejected

- **Inject into on-disk spec/hardening text** — mutates authored artifacts, blurs
  the lead-curated `_learnings.md` boundary. Injection belongs in the prompt.
- **Reuse `retrieve` with description as `errors_text`** — conflates two query
  intents and can't do area proximity (no `target_file` to match on).

## Files to change

Engine:

1. `memory.py` — `_SCHEMA` gains `target_file`; generalize the 0052 migration to
   `_migrate_column`; `record(...)` gains `target_file`; new `retrieve_gotchas(
   target_file, description, language, limit)`.
2. `server.py` — `memory(...)` tool gains `target_file` + `description` params and
   the `action="gotchas"` branch; `record` branch threads `target_file`.

Prompt/flow (project-root copies, per `CLAUDE.md`):

3. `context/flows/build-spec.md` — gotchas call before Generate; `target_file` on
   record calls.
4. `context/flows/build-ticket.md` — gotchas call in Step 4c; `target_file` on
   record calls; update the memory-contract note so it states memory now *also*
   feeds generation (curated files still never auto-written).
5. `context/harness-reference.md` — document `gotchas` in the memory contract.
6. `README.md` — note memory now feeds generation, not just repair.

## Verification

Unit tests (`tests/`), mirroring the 0052 migration tests:

1. **Back-compat:** a DB with `resolution` but no `target_file` triggers the new
   `_migrate_column` once; legacy `record`/`retrieve` round-trips unchanged.
2. **gotchas filter:** `escalated` records excluded by default; only `passed`
   surface, and their `resolution` appears in the narrative.
3. **Area proximity:** exact-`target_file` record ranks above same-language records
   elsewhere.
4. **Language fence:** a TS-gate record does not surface for `language='python'`.
5. **Empty corpus:** `gotchas` on a fresh DB returns empty string.

Flow dry run: build spec A in an area, let a gate fail-then-pass (recording a
`passed` row with `target_file` + `resolution`), then build spec B in the same area
and confirm the gotcha block — including the fix — appears in B's generation
context *before* its first gate.
