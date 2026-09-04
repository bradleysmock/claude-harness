# Solution

**Ticket**: 0076
**Title**: Local context packages

## Approach

Add `context_rank.py`: `gather_context()` ranks `rg -n` hits by
keyword/co-occurrence overlap (reusing `memory.py`'s tokenizer via a new
public alias), with an optional `ast-grep` structural pass. Named
`context_rank`, not `context_fetch` — `server.py` already exposes an
unrelated MCP tool called `context_fetch` (used by `build-spec.md`); reusing
that name would make two unrelated things look like one. The pack caches to
`.harness/context/<ticket>.md` keyed on `(query, HEAD, dirty-tree state)`.

## Components

| Component | Responsibility |
|---|---|
| `context_rank.py` | Pure ranking + its own exec helper; `describe_environment` for caller-side logging |
| `memory.py` | Gains a public `tokenize` alias for `_tokenise` |
| `commands/problem.md` (harness-combined) | Generates/loads the pack right after Phase 2 |
| `context/flows/build-ticket.md` Step 1 | Generates/loads the pack right after resolving `problem.md`'s path |
| `.gitignore` | `.harness/context/` ignored, like `.harness/craft/` |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Rename to `context_rank.py` | Avoids colliding with the live `context_fetch` MCP tool in `server.py` |
| Own `_exec`-shaped helper, modeled on `gates/go.py` | `gates/python.py`'s `_exec` is sandbox-bound; its own `_exec_dir(cmd, directory, timeout)` is the closer analog but is still private-by-convention, so a fresh helper is cleaner than reaching into another module's internals |
| Public `tokenize` alias in `memory.py` | `_tokenise` is private-by-convention; `context_rank.py` is its first production (non-test) cross-module consumer |
| `describe_environment()` separate from `gather_context()` | Keeps ranking genuinely pure; logging happens at the caller, the actual I/O boundary |
| Cache key includes `git status --porcelain` | A same-`HEAD` repair-round edit must still invalidate a stale pack |

## Decisions (resolves source doc's Checkpoint-1 questions + corrections)

- **Recency weighting**: out of scope for v1, a follow-up once proven.
- **Pack-size cap**: `max_snippets` (default 5) + `MAX_TOTAL_LINES`
  constant, not a `_standards.md` knob yet.
- **Regenerate on `/build` re-entry**: the `(query, HEAD, dirty-tree)`
  cache key already answers this — no special-casing needed.
- **Target subtree**: `harness-combined/` explicitly — the repo has other
  plugin trees (`claude-plugin/`, `harness-full`) with different shapes.
- **Corrections**: renamed `context_fetch.py` -> `context_rank.py` (name
  collision); `_exec` reuse claim was wrong (sandbox-bound) — implements
  its own, modeled on `gates/go.py`'s instead.

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1/2/3    | Unit        | `gather_context` ranks a needle file correctly; imports `memory.tokenize` |
| FR-4        | Unit        | Own exec helper runs `rg`/`ast-grep` as argv lists with a timeout |
| FR-5        | Unit        | `rg` absent -> empty pack; `ast-grep` absent -> ripgrep-only; neither raises or logs internally |
| FR-6/7      | Unit        | Size caps enforced; cache key reacts to query/`HEAD`/dirty-tree changes |
| FR-8/9/10   | Integration | `/problem` Phase 2->3 and `build-ticket.md` Step 1 each produce/load a pack and surface `describe_environment()`'s message when non-`None`; `.harness/context/` gitignored |

## Tradeoffs / Risks

- **Query = `problem.md` text**: `/problem` Phase 0-2 gets no pack —
  acceptable, those phases define the problem, not the fix.
- **Dirty-tree hashing adds a `git status` call per check**: small fixed
  cost for correctness across repair-round resumes.
- **`describe_environment`/`gather_context` could disagree** if the
  environment changes between calls — mitigated by pairing both
  back-to-back at each of FR-8/FR-9's two call sites, not just one.

## Implementation Order

1. Failing unit tests for ranking + `memory.tokenize` reuse (FR-1-3);
   implement `gather_context`'s ripgrep path.
2. Failing unit test for the own exec helper and both degrade paths
   (FR-4/5); implement.
3. Failing unit tests for size caps and the dirty-tree-aware cache key
   (FR-6/7); implement.
4. Failing integration tests + wire `commands/problem.md`'s Phase 2->3
   load (FR-8) and `build-ticket.md` Step 1 (FR-9).
5. Add `.harness/context/` to `.gitignore` (FR-10); document in
   `context/harness-reference.md`.
