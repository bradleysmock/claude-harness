# Design: Failure-memory forward-injection (proactive gotchas)

**Date:** 2026-06-18
**Status:** Proposed (Checkpoint 1 pending)
**Author:** Bradley + Claude

## Problem

Failure memory (`memory.py`, `.harness/memory.db`) is persistent and cross-spec,
but it is **consumed reactively only**. `memory(action="retrieve", ...)` fires
exclusively inside the repair loop, *after* a gate has already failed
(`build-spec.md:28`, `build-ticket.md:91`). The harness states this directionality
itself: *"the BM25 failure trail … is consulted only by `memory(action="retrieve")`
during repair — it never feeds back … automatically"* (`build-ticket.md:31`).

So a failure mode that was hit and resolved in spec A never shapes the **first**
generation attempt of spec B in the same area. The model re-derives the same
mistake, fails the gate, and only then is shown the past failure. The corpus
exists; the forward arrow does not. This is the "Gotchas section shapes
generation" pattern from Anthropic's harness — present in our repair loop,
absent from our generation step.

## Goal

Feed the persisted failure corpus **forward** into the generation step, so the
first attempt pre-empts known, area-local failure modes — without changing the
existing reactive repair path, the gate engine, or the spec schema's meaning.

## Non-goals

- Replacing the reactive `retrieve` path. It stays exactly as-is; this is purely
  additive.
- Embeddings / semantic retrieval. Keep BM25-only, consistent with `memory.py`.
- Auto-editing `.tickets/_learnings.md`. That file is lead-curated by contract
  (`build-ticket.md:31`); forward-injection feeds the **generation prompt**, not
  the curated files.
- Cross-project memory. Memory stays per-project (`.harness/memory.db`).

## Why the current corpus can't be queried at generation time

`retrieve_similar(errors_text, gate, ...)` keys on **error text** — which does
not exist yet when generation starts. To retrieve before the first gate, we must
key on the spec's *domain signals* instead: the `target_file` and `description`.
The stored records carry `spec_id`, `gate`, `errors_text`, `outcome` — but **no
`target_file`**, so today there is no way to ask "what failed before in this area."

## Approach (chosen: Approach A — domain-keyed `gotchas` action)

One additive column, one new memory action, two flow-step edits.

### 1. Schema: record the target area

Add a nullable `target_file` column to `failure_records`. Back-compat for
existing DBs: on `_init_db`, if the column is absent, `ALTER TABLE failure_records
ADD COLUMN target_file TEXT`. `_SCHEMA`'s `CREATE TABLE` includes it for fresh DBs.

`record(...)` and `memory(action="record", ...)` gain an optional `target_file`
parameter (default `""`), threaded from the spec already in hand at record time
(both build flows have `spec.target_file` loaded). Old call sites that omit it
keep working — the column is simply NULL/empty.

### 2. New retrieval mode: `gotchas`

`memory(action="gotchas", target_file=, description=, language=, project_root=,
limit=3)` returns a compact "Known gotchas in this area" block, or empty string
when the corpus has nothing relevant.

Selection and ranking (all in `SQLiteFailureMemory`, mirroring `retrieve_similar`):

- **Filter:** `outcome = 'passed'` only. A resolved failure is an *actionable*
  gotcha — we know the failure mode *and* that it is surmountable, so surfacing
  it pre-empts without false alarm. (`escalated` records are noisier and may be
  environmental; surfacing them is a follow-up toggle, off by default.)
- **Filter:** `gate` restricted to the gates for `language` (so a TS lint gotcha
  doesn't surface into a Python generation). Reuse the language→gate-name map the
  gate suite already defines.
- **Rank:** area proximity first — exact `target_file` match, then same-directory
  match — then BM25 over `description` tokens against the stored record tokens, as
  a tiebreaker so the most textually-similar past failures float up.
- **Cap:** `limit` (default 3), each narrative truncated like `retrieve_similar`.

Format (intentionally short — this rides in the generation prompt):

```
Known gotchas in this area (resolved past failures):
  ⚠ <gate> previously failed on <target_file or dir>: <error excerpt>
    → resolved on attempt N; pre-empt it.
```

### 3. Inject at generation, in both build flows

- `build-spec.md` — before the **Generate** step (currently line 22), call
  `memory(action="gotchas", target_file=spec.target_file, description=spec.description,
  language=language, project_root=project_root)`. If non-empty, prepend the block
  to the generation context as a hard "avoid these known failure modes" note.
- `build-ticket.md` — same, in **Step 4c** ("Generate implementation and tests"),
  per spec, using that spec's `target_file` / `description`.

The reactive `retrieve` calls (`build-spec.md:28`, `build-ticket.md:91`/`155`)
are untouched. A failure now informs *both* its own repair loop (reactive) and
future generations in the same area (proactive).

### 4. Thread `target_file` into the existing `record` calls

The on-pass / on-exhaustion `memory(action="record", ...)` calls in both flows add
`target_file=spec.target_file`. Without this, newly recorded failures would not be
retrievable by `gotchas` (only by the legacy error-keyed `retrieve`). This is the
write half that makes the read half useful going forward.

## Alternatives considered and rejected

- **Approach B — inject into the spec/hardening text on disk.** Mutates authored
  artifacts and blurs the lead-curated `_learnings.md` boundary. Rejected:
  forward-injection belongs in the ephemeral prompt, not on disk.
- **Approach C — reuse `retrieve` with the description as `errors_text`.** Avoids
  the schema change but conflates two query intents and can't do area proximity
  (no `target_file` to match on). The column is cheap and makes intent explicit.

## Files to change

Engine:

1. `memory.py` — `_SCHEMA` gains `target_file`; `_init_db` runs the idempotent
   `ALTER TABLE`; `record(...)` gains `target_file`; new `retrieve_gotchas(
   target_file, description, language, limit)`.
2. `server.py` — `memory(...)` tool gains `target_file` and `description` params
   and the `action="gotchas"` branch; `record` branch threads `target_file`.

Prompt/flow (project-root copies, per `CLAUDE.md`):

3. `context/flows/build-spec.md` — gotchas call before Generate; `target_file` on
   the record calls.
4. `context/flows/build-ticket.md` — gotchas call in Step 4c; `target_file` on the
   record calls; update the line-31 note to state memory now *also* feeds
   generation (the curated files are still never auto-written).
5. `context/harness-reference.md` — document the `gotchas` action in the memory
   contract section.
6. `README.md` — note that failure memory now feeds generation, not just repair.

## Verification

Unit tests (`tests/`), mirroring `test_gate_runner_polyglot.py` style:

1. **Back-compat:** opening an existing DB without `target_file` triggers the
   `ALTER TABLE` and leaves prior records readable; legacy `record`/`retrieve`
   round-trips unchanged.
2. **gotchas filter:** records with `outcome='escalated'` are excluded by default;
   only `passed` records surface.
3. **Area proximity:** given two resolved failures — one on the spec's exact
   `target_file`, one elsewhere — the exact-match record ranks first.
4. **Language fence:** a TS-gate record does not surface for a `language='python'`
   query.
5. **Empty corpus:** `gotchas` on a fresh DB returns empty string (generation
   proceeds with no injected block).

Flow-level dry run: build spec A in an area, let it fail-then-pass a gate (so a
`passed` record with `target_file` lands), then build spec B in the same area and
confirm the gotcha block appears in B's generation context *before* its first
gate run.
