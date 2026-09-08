# Design: Local context packages

**Date:** 2026-09-03
**Status:** Proposed (not yet ticketed)
**Author:** Bradley + Claude
**Origin:** Comparison against agentic-dev-platform's Repository Intelligence
component, which builds a ranked "briefing pack" of the most relevant code for a
task from SCIP/Zoekt/ast-grep before the agent starts. This project's own
CLAUDE.md leans on GitNexus for the same purpose — a local index, not a hosted
service — which is the proof this is achievable without new infrastructure.

## Problem

`/problem` and `/build` hand the model static context files
(`context/harness-reference.md`, panels, rules) plus whatever the model chooses
to explore on its own. There's no ranked, task-relevant snippet pack assembled
up front — every ticket starts exploration from zero, and a large or unfamiliar
codebase costs real turns just locating the relevant files.

## Goal

A `context_fetch` step that assembles a ranked snippet pack from local tools
already available (ripgrep, optionally ast-grep) — no indexing daemon, no new
service — cached to disk per ticket so repeated `/build` invocations don't
re-scan, and injected into `/problem` and `/build` the same way
`_standards.md`/`_learnings.md` already are.

## Non-goals

- A persistent code index (SCIP/Zoekt-equivalent). This is search-and-rank at
  request time, not a maintained database — the harness has no long-running
  process to keep an index warm.
- Replacing the model's own exploration. The pack is a head start, not a
  substitute — the model can still read further as needed.

## Architecture

### `context_fetch.py` (new)

```python
@dataclass(frozen=True)
class Snippet:
    file: str
    lines: tuple[int, int]
    text: str
    score: float

def gather_context(
    query: str, project_root: Path, max_snippets: int = 5
) -> list[Snippet]: ...
```

Ranking is a heuristic score, not a model call: keyword/identifier overlap
between `query` (the ticket's `problem.md` text) and `rg -n` hit lines, weighted
by how many distinct query terms co-occur in the same file. Reuses
`memory.py`'s `_tokenise` function rather than writing a second tokenizer — the
harness already has one BM25-lite tokenizer; a second, slightly different one
would be a silent inconsistency waiting to confuse someone debugging a ranking.

An optional ast-grep pass runs when the query looks like a symbol reference
(e.g. "callers of `resolve_ticket`") — structural match instead of plain text.
If the `ast-grep` binary is absent, that pass is skipped silently and ranking
falls back to ripgrep only, the same "optional tool absent → degrade, don't
fail" pattern `gates/go.py` already uses for `staticcheck`
(`TOOL_SKIPPED`, not `TOOL_ERROR`).

### Caching

The assembled pack is written to `.harness/context/<ticket>.md`, keyed by a hash
of `(query text, git rev-parse HEAD)`. A cache miss (new query text, or `HEAD`
has moved since the cached pack was written) regenerates; a hit is reused as-is.
This mirrors the checkpoint-invalidation pattern already in the harness (ticket
0051) rather than inventing a new staleness rule.

### Injection

`context/flows/problem.md` (or wherever `/problem` currently assembles its
prompt) loads `.harness/context/<ticket>.md` via the same `@path` include
mechanism already used for `_standards.md`/`_learnings.md`. Additive: absent
file, no change in behavior.

## Files to change

- `context_fetch.py` — new.
- `commands/problem.md`, `commands/build.md` (or the underlying
  `context/flows/*.md`) — generate the pack and include it.
- `.gitignore` — ignore `.harness/context/` (ephemeral, like
  `.harness/results/`).
- `context/harness-reference.md` — document the step and its cache.
- `tests/test_context_fetch.py` — new.

## Verification

1. **Ranking**: a fixture repo with a known "needle" file scores it above
   unrelated files for a query naming its distinctive identifiers; ranking is
   deterministic given identical inputs (no LLM call inside `gather_context`
   itself).
2. **Cache key**: an unchanged `(query, HEAD)` reuses the cached pack; a moved
   `HEAD` regenerates.
3. **Degraded path**: with `ast-grep` absent (simulate via `PATH` manipulation
   in the test), ranking still succeeds via ripgrep alone — no `TOOL_ERROR`.
4. **Integration**: `/problem` on a real multi-file ticket description produces
   a pack that includes the actually-relevant file.

## Open decisions for Checkpoint 1

1. Should ranking also weight recently-changed files (`git log` recency)
   alongside keyword match, the way the platform's context package also draws
   on coverage/build metadata — or is that a follow-up once plain keyword
   ranking is proven?
2. What's the hard cap on pack size (snippet count or total lines) to avoid
   crowding out the model's own context budget, and where does that number
   live — a constant, or a `_standards.md` knob?
3. Does the pack regenerate on every `/build` re-entry (e.g. after
   `changes-requested`), or only on the first `/problem`/`/build` for a ticket,
   trusting the model's own follow-up reads after that?
