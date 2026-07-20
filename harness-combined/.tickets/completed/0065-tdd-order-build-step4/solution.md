# Solution

**Ticket**: 0065
**Title**: TDD-order build Step 4: red test gate before implementation; write files directly instead of fenced blocks

## Approach

Split Step 4 into: write the spec's test file directly → run a red-gate check,
exactly scoped to the new test node(s), classifying `red` / `blocking` /
`tool_error` → on `red`, write implementation directly. `blocking` retries to
`MAX_REPAIR_ATTEMPTS`; `tool_error` escalates immediately (no retry). Both
exhaustion paths skip-and-continue like Step 4e's existing precedent, never
halting the build. Writes go straight to worktree files — the fenced
`# implementation` / `# tests` instruction is dropped. Step 4e's full-suite
`gate_run_on_dir` gate is untouched.

## Components

| Component | Responsibility |
|-----------|-----------------|
| `gates/red_gate.py::check_red()` (new) | Classifies `red`/`blocking`/`tool_error`. Python/Go/Rust already expose `_run_*_collect_dir`/`_parse_*` pairs returning `(parsed_ok, present, failing)` — reused directly, re-parameterized to an exact node-id filter (pytest node id, `go test -run '^Name$'`, `cargo test --exact <fqn>`). TypeScript's `_parse_jest_json` returns only `(parsed_ok, failing)`; it gains a small extension to also collect `present` ids from `assertionResults` already in its JSON payload (status passed/failed), matched with an anchored `-t` pattern scoped to the target file. `tool_error` = `parsed_ok is False`. A collection/import error is `red` only when its message/traceback names the not-yet-created target — not any collection failure in the file |
| `gates/red_gate.py::next_action()` (new) | Pure decision function `(classification, attempt, max_attempts) -> RETRY \| ESCALATE_SKIP \| PROCEED`, independently testable from flow prose |
| New MCP tool `gate_run_red_check` | Wraps `check_red()`/`next_action()`; catches any exception from either and reports `tool_error` rather than letting it propagate or default to `PROCEED` |
| `context/flows/build-ticket.md` Step 4 edit | Sub-step split; documents skip-and-continue on `ESCALATE_SKIP`; removes fenced-block generation language |
| `tests/test_red_gate.py` (new) | Coverage: classification per language, substring-collision attribution (e.g. `test_foo` vs `test_foo_bar` in one file), `next_action()` transitions |
| `tests/test_0065_build_flow.py` (new) | Content-verification on `build-ticket.md` |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Reuse Python/Go/Rust's existing `(parsed_ok, present, failing)` parsers as-is; extend TypeScript's minimally | Three of four languages need no new parsing logic; TS's gap is additive (present-tracking from data its JSON already returns), not a rewrite |
| Exact/anchored node targeting (`-run '^Name$'`, `--exact`, anchored `-t` + file scope), not substring filters | Unanchored filters (`go test -run Foo` also matches `FooBar`) would misattribute an unrelated pre-existing failure to the new test |
| New pure `next_action()` decision function | Makes retry/escalate/skip (FR-4/5/6) directly unit-testable, not embedded only in flow prose |
| Narrow the collection-error → `red` fallback to target-name matching | A blanket "node id absent from `present`" fallback would also fire on unrelated pre-existing collection breakage, a false `red` |
| New narrow MCP tool instead of extending `gate_run_on_dir` | The full multi-gate suite would spuriously fail on lint/type errors for code that doesn't exist yet |
| Reuse `MAX_REPAIR_ATTEMPTS`; validate the test path is contained within the worktree root | Avoids a new tunable; contains a now-externally-reusable path argument per `CLAUDE.md`'s path rule |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-1, FR-7 | Content | `build-ticket.md` documents write-test-first, direct-write, drops fenced-block text |
| FR-2, FR-3 | Integration | `check_red()` (real subprocess per language): failing new node → `red`; all-passing → `blocking` |
| FR-3 (collision) | Integration | `test_foo` vs pre-existing failing `test_foo_bar` in one file — new node attributed correctly, not cross-matched |
| FR-3 (collection, tool_error) | Integration | Import error naming the missing target → `red`; unrelated collection breakage → not `red`; crashed runner → `tool_error` |
| FR-4, FR-5, FR-6 | Unit | `next_action()`: `blocking` retries to budget, `tool_error` escalates on first occurrence, exhaustion → `ESCALATE_SKIP` |
| FR-8 | Integration | Existing Step 4e gate/repair tests unchanged — regression guard |
| FR-9 | Unit | Classification is pure Python; an injected exception is caught and reported `tool_error`, never propagated |
| FR-10 | Integration | New node correctly attributed apart from an unrelated pre-existing failure in the same file |

## Tradeoffs

- **Chose skip-and-continue (mirroring Step 4e) over halting the whole build on
  exhaustion because**: one exhaustion UX pattern in the flow, not two.
- **Chose exact/anchored node targeting over the simpler substring filters
  each tool defaults to because**: substring collision is a real, silent
  misattribution risk, not a hypothetical edge case.
- **Accepting risk of**: a test that structurally can't fail exhausting the
  retry budget — mitigated by the same-sized budget as the existing repair loop.

## Risks

- TypeScript's `present`-tracking extension is new code, not reuse — the one
  language where regression is possible; covered by its own test rows above.
- The narrowed collection-error `red` fallback is a heuristic on error text,
  not a structural guarantee — scoped to the common case (spec's own target
  module missing); any other collection failure reports `tool_error`, never a
  silent false `red`.

## Implementation Order

1. `tests/test_red_gate.py`: coverage for `check_red()`/`next_action()` across
   languages, classifications, and the substring-collision case (written
   first — red).
2. `gates/red_gate.py`: `check_red()` + `next_action()` to turn 1 green.
3. New MCP tool `gate_run_red_check` wrapping both, with exception containment.
4. Rewrite `build-ticket.md` Step 4: sub-step split, classification +
   skip-and-continue, direct-write instructions, drop fenced-block language.
5. `tests/test_0065_build_flow.py`: content-verification on the doc edit.
