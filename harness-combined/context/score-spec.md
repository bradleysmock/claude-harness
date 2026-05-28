# Score-spec procedure

Lightweight pre-implementation spec validator. Checks that a ticket's `requirements.md` and `solution.md` are specific enough to implement against.

## Checks

Read `.tickets/XXXX-<slug>/requirements.md` and `.tickets/XXXX-<slug>/solution.md`. Apply:

1. **FR count** — `requirements.md` has at least 3 numbered functional requirements (lines matching `^\s*\d+\.\s`).
2. **Imperative language** — every FR uses "must" or "shall", not "should" / "may" / "could".
3. **Test-plan coverage** — every FR number in `requirements.md` appears as a row in `solution.md`'s Test Plan table, and every FR number in the Test Plan exists in `requirements.md` (no phantom references).
4. **Implementation Order present** — `solution.md` has a non-empty `## Implementation Order` section with at least one ordered item.
5. **No placeholders** — neither file contains unfilled template markers. Flag any of these patterns (search outside fenced code blocks):
   - **Bare keywords**, case-insensitive: `TODO`, `TBD`, `FIXME`, `XXX`, `???`
   - **Bracketed prose** — any `<...>` span whose content contains **whitespace**. The artifact templates emit hints like `<2–4 sentences. Focus on the problem, not the solution.>`, `<Bullet list: what must be true when this is resolved.>`, `<Numbered list. Each item is a testable statement: "The system must...">`, `<what is tested at unit level>`, `<Ordered list of implementation steps. …>`. All of these contain whitespace inside the brackets and must be replaced before scoring. Regex: `<[^<>\n]*\s[^<>\n]*>`.
   - **Stub table cells** — a markdown table row where every non-header cell is literally `...` (e.g. `| ... | ... |`). This is the template's "fill in this row" marker.

   Single-token bracket spans like `<title>`, `<slug>`, `<branch>` are status-line back-references rather than prose placeholders; do not flag them on their own. The other checks (FR count, imperative language, test-plan coverage) will catch genuinely empty files.

   For each placeholder hit, report the file path and a `line:column` location with the offending span so the lead can jump to it.
6. **Acceptance criteria** — `requirements.md` has at least 2 binary acceptance criteria.

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

Verdict: PASS | WARN | BLOCK
```

**Verdict rules**:
- Any BLOCK → overall BLOCK
- Any WARN, no BLOCK → overall WARN
- Otherwise PASS

**Severity per check**:
- FR count, Imperative language, Test-plan coverage, No placeholders → BLOCK if failing
- Implementation Order present, Acceptance criteria → WARN if failing
