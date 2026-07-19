# Score-spec procedure

Lightweight pre-implementation spec validator. Checks that a ticket's `requirements.md` and `solution.md` are specific enough to implement against.

## Checks

Read `.tickets/XXXX-<slug>/requirements.md` and `.tickets/XXXX-<slug>/solution.md`. Apply:

**Run the validator for checks 1-6.** `validators/score_spec.py <ticket-dir>` implements
checks 1-6 deterministically and prints the six mechanical `[PASS|WARN|BLOCK]` lines —
run it and use its output rather than re-deriving these checks by re-reading the prose
below. The model performs **only** check 7 (FR testability) itself, judged and
WARN-only as documented at check 7 below; see **Composition** for how the two outputs
combine into one final report and verdict.

1. **FR count** — `requirements.md` has at least 3 numbered functional requirements (lines matching `^\s*\d+\.\s`). Scored on the `## Functional Requirements` section only, counting top-level (unindented) numbered items — nested numbered sub-items and NFRs are not counted.
2. **Imperative language** — every FR uses "must" or "shall", not "should" / "may" / "could". A weak modal is flagged only outside inline-code spans; an FR containing no modal at all passes (vagueness falls to judged check 7).
3. **Test-plan coverage** — every FR number in `requirements.md` appears as a row in `solution.md`'s Test Plan table, and every FR number in the Test Plan exists in `requirements.md` (no phantom references).
4. **Implementation Order present** — `solution.md` has a non-empty `## Implementation Order` section with at least one ordered item.
5. **No placeholders** — neither file contains unfilled template markers. Flag any of these patterns (search outside fenced code blocks and inline single-backtick spans):
   - **Bare keywords**, case-insensitive: `TODO`, `TBD`, `FIXME`, `XXX`, `???`
   - **Bracketed prose** — any `<...>` span whose content contains **whitespace**. The artifact templates emit hints like `<2–4 sentences. Focus on the problem, not the solution.>`, `<Bullet list: what must be true when this is resolved.>`, `<Numbered list. Each item is a testable statement: "The system must...">`, `<what is tested at unit level>`, `<Ordered list of implementation steps. …>`. All of these contain whitespace inside the brackets and must be replaced before scoring. Regex: `<[^<>\n]*\s[^<>\n]*>`.
   - **Stub table cells** — a markdown table row where every non-header cell is literally `...` (e.g. `| ... | ... |`). This is the template's "fill in this row" marker.

   Single-token bracket spans like `<title>`, `<slug>`, `<branch>` are status-line back-references rather than prose placeholders; do not flag them on their own. The other checks (FR count, imperative language, test-plan coverage) will catch genuinely empty files.

   For each placeholder hit, report the file path and a `line:column` location with the offending span so the lead can jump to it.
6. **Acceptance criteria** — `requirements.md` has at least 2 binary acceptance criteria, counted within the `## Acceptance Criteria` section only.
7. **FR testability** *(judged, WARN-only)* — for **each** functional requirement,
   judge whether a failing test is derivable from the FR sentence **alone**: it must
   name a concrete **actor** (who/what acts), a specific **action**, and an
   **observable outcome** a test could assert. An FR that could only be satisfied or
   refuted by re-reading other requirements, or whose outcome is subjective
   ("correctly", "properly", "as expected", "user-friendly") with nothing measurable,
   is **flagged**. Report one line per flagged FR with a one-line reason (see Output).
   Flag only genuinely underivable FRs — never style, tone, or wording nits; a
   testable FR that merely reads awkwardly passes. This check **only ever WARNs**; it
   has no BLOCK authority and never changes the deterministic verdict.

   Worked examples:
   - **Passes** — "The export command must write a `report.json` file to the output
     directory and exit non-zero if the directory is missing." Actor (export command),
     action (write / exit), observable outcome (file present; exit code) — a failing
     test writes itself.
   - **Flagged** — "The system must handle errors correctly." No concrete actor, no
     specific action, and "correctly" names no observable outcome. *Reason: no
     assertable outcome — "correctly" is subjective and no actor/action is specified.*

## Composition

`validators/score_spec.py`'s printed report covers only checks 1-6. To produce the
full seven-check report: insert the judged FR-testability line (and its indented
`FR-<n>: <reason>` sub-lines, if any) **above** the validator's `Verdict:` line, then
**recompute** the final verdict across all seven lines using the Verdict rules below —
never just relay the validator's own (six-check) verdict as final. A mechanical PASS
combined with a testability WARN therefore yields an overall WARN.

## Output

Print a structured report:

```
score-spec: XXXX-<slug>

[PASS|WARN|BLOCK] FR count
[PASS|WARN|BLOCK] Imperative language
[PASS|WARN|BLOCK] Test-plan coverage
[PASS|WARN|BLOCK] Implementation Order present
[PASS|WARN|BLOCK] No placeholders
[PASS|WARN|BLOCK] Acceptance criteria
[PASS|WARN] FR testability
  - FR-<n>: <one-line reason this FR is not testable>   # one line per flagged FR; omit when none

Verdict: PASS | WARN | BLOCK
```

The `FR testability` line reports `PASS` when every FR is testable, or `WARN` with one
indented `FR-<n>: <reason>` line per flagged FR. This per-FR testability output is
carried verbatim into the `/problem` Phase 6 display and the Checkpoint 1 verdict.

**Verdict rules**:
- Any BLOCK → overall BLOCK
- Any WARN, no BLOCK → overall WARN
- Otherwise PASS

**Severity per check**:
- FR count, Imperative language, Test-plan coverage, No placeholders → BLOCK if failing
- Implementation Order present, Acceptance criteria, FR testability → WARN if failing

Only the four checks above (FR count, Imperative language, Test-plan coverage, No
placeholders) carry BLOCK authority. `FR testability` is a judged check and is capped
at WARN so the deterministic checks keep sole control of the BLOCK verdict.
