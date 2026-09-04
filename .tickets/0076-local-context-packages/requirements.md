# Requirements

**Ticket**: 0076
**Title**: Local context packages

## Functional Requirements

1. The system must provide `context_fetch.py`: a frozen `Snippet`
   dataclass (`file`, `lines`, `text`, `score`) and `gather_context(query,
   project_root, max_snippets=5) -> list[Snippet]`.
2. Ranking must be a heuristic — keyword overlap between `query` and
   `rg -n` hits, weighted by co-occurring terms per file — no LLM call, so
   identical inputs give identical output.
3. `gather_context` must reuse `memory.py`'s `_tokenise`, not a second
   tokenizer.
4. `rg`/`ast-grep` must run as argv lists (`subprocess.run`, `shell=False`,
   with a timeout), matching `gates/python.py`'s `_exec` convention.
5. An optional `ast-grep` structural pass runs for symbol-reference-shaped
   queries; if the binary is absent (`shutil.which`), skip it with one
   visible log line and fall back to ripgrep-only — never raise.
6. The pack is capped by `max_snippets` (default 5) and a total-line
   ceiling (`MAX_TOTAL_LINES`, a module constant) — not a `_standards.md`
   knob in this iteration.
7. The pack is written to `.harness/context/<ticket>.md`, keyed by a hash
   of `(query text, git rev-parse HEAD)`; an unchanged key reuses it, a
   changed key regenerates.
8. `commands/problem.md` must generate/refresh the pack right after Phase
   2 writes `problem.md` (using its text as `query`), loading it via
   `@.harness/context/<ticket>.md` for Phases 3-4 — not earlier, since
   `problem.md` doesn't exist yet at Phase 0/1.
9. `context/flows/build-ticket.md` must generate/refresh the pack early in
   Step 1 (`problem.md` already exists there), before spec generation.
10. `.harness/context/` must be gitignored, matching `.harness/craft/`.

## Non-Functional Requirements

1. No indexing daemon; search-and-rank at request time, local tools only.
2. A cache miss or absent file must never block `/problem`/`/build`.
3. `gather_context` stays pure; FR-5's log line is its only side effect.

## Test Strategy

| Type        | Rationale                                              |
|-------------|-----------------------------------------------------------|
| Unit        | Needle file ranks above unrelated ones, deterministically |
| Unit        | Cache key: unchanged `(query, HEAD)` reuses; either changing regenerates; `ast-grep` absent degrades to ripgrep-only |
| Integration | `/problem` Phase 2->3 and `/build` Step 1 each produce/load a pack |

## Acceptance Criteria

- Fixture "needle" file scores above unrelated files; identical inputs
  produce identical output; unchanged `(query, HEAD)` reuses the cache,
  either changing regenerates.
- `ast-grep` absent still produces a ranked pack via ripgrep alone.
- `/problem` generates the pack only after Phase 2; `/build` generates it
  in Step 1 before spec generation.

## Open Questions

None — resolved as decisions in `solution.md § Decisions`.
