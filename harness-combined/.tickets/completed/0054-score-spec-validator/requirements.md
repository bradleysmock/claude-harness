# Requirements

**Ticket**: 0054
**Title**: Score-spec Python validator: mechanical checks 1-6

## Functional Requirements

1. The validator must report BLOCK on the FR-count check when the Functional
   Requirements section of `requirements.md` has fewer than 3 numbered items
   (section-scoped, top-level unindented items only — nested sub-lists not counted).
2. The validator must report BLOCK on the imperative-language check when any FR
   contains a weak modal (score-spec check-2 list) outside inline code; an FR with
   no modal at all must not be flagged — vagueness falls to judged check 7.
3. The validator must report BLOCK on the test-plan-coverage check when any FR number
   lacks a Test Plan row in `solution.md` or the Test Plan references a nonexistent FR.
4. The validator must report BLOCK on the no-placeholders check on any check-5
   pattern hit outside code, listed as line:column plus span; the scanner must exempt
   backtick/tilde fences (info strings allowed) and inline single-backtick spans,
   and must scan content after an unclosed fence as unfenced.
5. The validator must report WARN when `solution.md` lacks an Implementation Order
   section with 1 or more ordered items, and WARN when the Acceptance Criteria
   section of `requirements.md` has fewer than 2 bullets (section-scoped).
6. The CLI must print the `score-spec: XXXX-<slug>` header (slug from the ticket
   directory basename), the six mechanical check lines, and the verdict line in the
   exact score-spec.md format, and must exit 0 on PASS, 1 on WARN, 2 on BLOCK.
7. The CLI must fail closed: missing or unreadable artifacts and internal exceptions
   must exit 2 with the reason on stderr, never a traceback-driven exit 1; argparse
   usage errors exiting 2 is the documented, deliberate behavior.
8. The validator must expose a pure `score(requirements_text, solution_text)`
   function returning per-check results; file I/O must live only in `main()`.
9. `context/score-spec.md` must direct consumers to run the validator for checks 1-6
   and judge only check 7, inserting the FR-testability line above the verdict and
   recomputing the final verdict (mechanical PASS plus testability WARN yields WARN).

## Non-Functional Requirements

1. Stdlib only; checks 1-3 reuse `gates/spec_remediate.py` loaded via
   `importlib.util.spec_from_file_location` (no package-init execution) — standalone
   in both the repo and the plugin cache.
2. The six check labels must be byte-identical to the score-spec.md output block;
   a regression test must pin the four BLOCK labels to `spec_remediate.RECIPE` keys.

## Test Strategy

| Type        | Rationale                                                        |
|-------------|------------------------------------------------------------------|
| Unit        | Each check: pass, fail, and edge fixtures via the pure `score()` |
| Integration | CLI end-to-end on fixture ticket dirs: report text + exit codes  |

## Acceptance Criteria

- CLI on a clean fixture ticket prints the header, 6 PASS lines, `Verdict: PASS`,
  and exits 0; a phantom Test Plan FR fixture exits 2 with BLOCK on coverage.
- A placeholder inside a fenced block is not flagged; after an unclosed fence it is
  flagged with line:column; an FR with no modal passes the imperative check.
- CLI on a ticket dir missing `solution.md` exits 2 with the reason on stderr.
- `context/score-spec.md` names the validator invocation for checks 1-6, scopes the
  model to check 7, and states the insert-and-recompute composition rule.
