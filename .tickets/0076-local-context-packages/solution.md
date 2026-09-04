# Solution

**Ticket**: 0076
**Title**: Local context packages

## Approach

Add `context_fetch.py`: `gather_context()` ranks `rg -n` hits by
keyword/co-occurrence overlap with `query` (reusing `memory.py`'s
`_tokenise`), with an optional `ast-grep` structural pass for
symbol-shaped queries. The pack caches to `.harness/context/<ticket>.md`
keyed on `(query, HEAD)`. Injection sits at the point each flow actually
has a `query` — corrected from the source doc's "inject the same way
`_standards.md` is," impossible for `/problem` before `problem.md` exists.

## Components

| Component | Responsibility |
|---|---|
| `context_fetch.py` | Ranking, caching, degrade-on-missing-tool |
| `commands/problem.md` | Generates/loads the pack right after Phase 2 |
| `context/flows/build-ticket.md` Step 1 | Generates/loads the pack before spec generation |
| `.gitignore` | `.harness/context/` ignored, like `.harness/craft/` |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Reuse `memory.py`'s `_tokenise` | One BM25-lite tokenizer, not a second, slightly different one |
| `subprocess.run([...], shell=False)` | Matches `gates/python.py`'s `_exec` — the codebase's one existing subprocess convention |
| Cache key `(query, HEAD)` | Mirrors ticket 0051's checkpoint-invalidation pattern instead of a new staleness rule |
| Pack generated at Phase 2 (not Phase 0) for `/problem` | `problem.md` is the query source; it doesn't exist before Phase 2 |

## Decisions (resolves source doc's Checkpoint-1 questions)

- **Recency weighting**: out of scope for v1 — plain keyword/co-occurrence
  only, kept simple and deterministic; a `git log`-recency term is a
  follow-up once this is proven.
- **Pack-size cap**: two module constants in `context_fetch.py` —
  `max_snippets` (default 5) and `MAX_TOTAL_LINES` — not a `_standards.md`
  knob yet; revisit if real usage needs per-project tuning.
- **Regenerate on `/build` re-entry**: no special-casing needed — the
  `(query, HEAD)` cache key already answers this; a resume regenerates
  only if `problem.md`'s text or `HEAD` actually changed.
- **Injection timing correction**: source doc cited a nonexistent
  `context/flows/problem.md` — `/problem` has no separate flow file, so
  `commands/problem.md` itself is edited, at the Phase-2-to-3 boundary.

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1/2/3    | Unit        | `gather_context` ranks a needle file correctly; reuses `_tokenise` |
| FR-4        | Unit        | `rg`/`ast-grep` invoked as argv lists with a timeout |
| FR-5        | Unit        | `ast-grep` absent (PATH manipulation) degrades to ripgrep-only, logs once, never raises |
| FR-6        | Unit        | Pack respects `max_snippets` and `MAX_TOTAL_LINES` |
| FR-7        | Unit        | Cache hit/miss on `(query, HEAD)` combinations |
| FR-8        | Integration | `/problem` generates the pack only after Phase 2, loads it for Phases 3-4 |
| FR-9/10     | Integration | `build-ticket.md` Step 1 generates/loads the pack; `.harness/context/` is gitignored |

## Tradeoffs / Risks

- **Query = `problem.md` text, not the raw request**: one consistent
  query-source, but `/problem` Phase 0-2 gets no pack — acceptable, since
  those phases define the problem, not the fix.
- **HEAD-keyed cache invalidates per worktree commit**: intentional —
  `gather_context` runs once per `/build` entry (Step 1), held in context
  for that session; only a later re-entry re-checks the key. No existing
  `rg`/`ast-grep` precedent — mitigated by matching `_exec` exactly.

## Implementation Order

1. Failing unit tests for ranking + `_tokenise` reuse (FR-1-3); implement
   `gather_context`'s ripgrep path.
2. Failing unit test for the `ast-grep` degrade path (FR-4/5); implement.
3. Failing unit tests for size caps and cache key (FR-6/7); implement.
4. Failing integration tests + wire `commands/problem.md`'s Phase 2->3
   load (FR-8) and `build-ticket.md` Step 1 (FR-9).
5. Add `.harness/context/` to `.gitignore`; document in
   `context/harness-reference.md`.
