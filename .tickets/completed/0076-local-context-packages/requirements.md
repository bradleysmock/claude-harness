# Requirements

**Ticket**: 0076
**Title**: Local context packages

**Target**: `harness-combined/` (distinct from `claude-plugin/`/`harness-full`).

## Functional Requirements

1. Provide `context_rank.py` (not `context_fetch.py` — `server.py` already
   registers an unrelated MCP tool of that name): a frozen `Snippet`
   (`file`, `lines`, `text`, `score`), `gather_context(query, project_root,
   max_snippets=5) -> list[Snippet]`.
2. Ranking is a heuristic — keyword overlap between `query` and `rg -Fn`
   (fixed-string, since `query` is free-form prose containing arbitrary
   characters) hits, weighted by co-occurring terms; deterministic.
3. `memory.py` must expose a public alias for `_tokenise` (e.g.
   `tokenize = _tokenise`) for `context_rank.py` to import.
4. `context_rank.py` implements its own argv-list, `shell=False`,
   timeout-bound exec helper (`cwd: str | Path`), modeled on
   `gates/go.py`'s `_exec` — not `gates/python.py`'s sandbox-bound one.
5. `gather_context` stays pure: absent `rg`/`ast-grep` degrades (ripgrep-
   only, or empty if `rg` missing) without raising or logging. A separate
   pure `describe_environment(project_root) -> str | None` reports the
   degrade state for the caller to log.
6. The pack is capped by `max_snippets` (default 5) and `MAX_TOTAL_LINES`
   (a module constant, not a `_standards.md` knob yet).
7. The pack is written to `.harness/context/<ticket>.md`, keyed by a hash
   of `(query, git rev-parse HEAD, git status --porcelain)` so an
   uncommitted edit invalidates a same-`HEAD` cache.
8. `commands/problem.md` generates/refreshes the pack right after Phase 2
   writes `problem.md`, loads it, and prints `describe_environment()`'s
   message when non-`None`.
9. `build-ticket.md` Step 1 does the same right after resolving
   `problem.md`'s path, before the spec-existence check.
10. `.harness/context/` is gitignored, matching `.harness/craft/`.

## Non-Functional Requirements

1. No indexing daemon; search-and-rank at request time, local tools only;
   a cache miss or absent `rg`/`ast-grep` never blocks `/problem`/`/build`.
2. `gather_context`/`describe_environment` stay pure; only the caller logs.

## Test Strategy

| Type        | Rationale                                              |
|-------------|-----------------------------------------------------------|
| Unit/Integ. | Needle ranks above unrelated files deterministically; cache key reacts to query/`HEAD`/dirty-tree; tool-absence degrades silently; `/problem`/`build-ticket.md` each produce/load+surface a pack |

## Acceptance Criteria

- Needle file scores above unrelated files; identical inputs match;
  changing query, `HEAD`, or the tree regenerates the cache.
- `rg`/`ast-grep` absence degrades without raising; only the caller logs.
- `/problem` (Phase 2) and `/build` (Step 1) each surface a non-`None`
  degrade message.

## Open Questions

None — resolved as decisions in `solution.md § Decisions`.
