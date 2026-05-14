Lightweight pre-implementation spec validator. Checks that a ticket's `requirements.md` and `solution.md` are specific enough to implement against. Runs automatically at the end of `/problem`'s Phase 5 and on demand.

## Ticket resolution

A ticket number argument is required. If none is provided, scan `.tickets/` for tickets with `status: solution`. If exactly one exists, use it.

## Checks

Read `.tickets/XXXX-<slug>/requirements.md` and `.tickets/XXXX-<slug>/solution.md`. Apply:

1. **FR count** — `requirements.md` has at least 3 numbered functional requirements (lines matching `^\s*\d+\.\s`).
2. **Imperative language** — every FR uses "must" or "shall", not "should" / "may" / "could".
3. **Test-plan coverage** — every FR number referenced in `requirements.md` appears in `solution.md`'s Test Plan table.
4. **Implementation Order present** — `solution.md` has a non-empty `## Implementation Order` section with at least one ordered item.
5. **No placeholders** — neither file contains `<TODO>`, `<placeholder>`, `<fill in>`, or `TBD`.
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

## Caller behavior

- `/problem` calls this before Checkpoint 1. If verdict is BLOCK, surface the failures in the checkpoint summary and recommend the lead reject.
- Standalone use: just prints the report.
