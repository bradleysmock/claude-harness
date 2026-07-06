# Solution

**Ticket**: 0034
**Title**: Requirements integrity review skill

## Approach

Add a new `requirements-review` skill at `skills/requirements-review/SKILL.md`. The skill is invoked with a ticket number, resolves the slug from the `.tickets/` directory (with path containment validation), reads `problem.md` and `requirements.md`, spawns a read-only subagent to apply four named analysis dimensions, and writes a structured findings report to `requirements-findings.md`. Analysis is performed in a scoped read-only subagent (tools: Read, Grep, Glob only) to contain the prompt-injection surface — the untrusted ticket content never runs inside a context with file-write capability.

## Components

| Component | Responsibility | Key interface |
|-----------|---------------|---------------|
| `skills/requirements-review/SKILL.md` | Skill entry point: ticket resolution (with path containment check), guard clauses, subagent dispatch, report write | Invoked as `/requirements-review XXXX` |
| Ticket resolver (inline logic) | Reads `.tickets/` to match four-digit number to slug; validates resolved dir is a direct child of `.tickets/`, not a path escape or symlink | Input: XXXX → output: validated absolute path |
| Analysis subagent (read-only) | Applies four dimensions against problem.md + requirements.md; tools restricted to Read/Grep/Glob | Returns findings in a defined stanza format (one labeled block per finding: DIMENSION / DESCRIPTION / FIX); parent validates fields before writing output |
| `requirements-findings.md` (output) | Structured findings report with defined schema (header, findings block, summary line); distinct from gate-findings.md | Written by parent skill (not subagent) to `.tickets/XXXX-<slug>/` |
| `skills/requirements-review/fixtures/` | Persistent fixture ticket dirs: completeness-defect, testability-defect, coverage-defect, consistency-defect, clean | Used for regression testing after SKILL.md changes; eval re-run procedure documented in `skills/requirements-review/README.md` |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Read-only subagent for analysis | Scopes tool access — untrusted ticket content analyzed by a context with no write tools, mitigating Willison lethal trifecta; parent writes the output file after receiving findings |
| Path containment validation before any read | Fails closed against path traversal; ticket number is operator-supplied input |
| Persistent fixtures (not ephemeral) | Provides regression protection given analysis is LLM-driven and prompt changes can shift behavior silently |
| Defined output schema (header + findings block + summary line) | Gives downstream consumers and eval tests a stable contract to assert against |
| Four explicit dimension names with examples in SKILL.md | Completeness (problem → FR traceability) vs Coverage (success criteria → AC traceability) are distinct and must be explicitly differentiated to avoid ambiguous classification |
| No auto-repair | Keeps skill advisory; repair would require a separate skill to preserve separation of concerns |
| No 80-line hard cap on output | Replaced by per-finding format discipline (max 5 lines per finding) to avoid truncation of valid findings |
| Subagent stanza format + parent validation | Avoids Willison text-parsed detection hazard — parent checks required fields (DIMENSION / DESCRIPTION / FIX) before writing; malformed subagent return halts with error |
| Subagent findings echoed to operator before write | Satisfies CLAUDE.md observability rule for LLM calls without requiring separate log infrastructure; operator can see what the subagent returned and dispute findings before they are written to file |

## Test Plan

| Requirement | Test Type   | Scenario(s) | Oracle |
|-------------|-------------|-------------|--------|
| FR-1 (skill invocable on any ticket) | Integration | Invoke on ticket 0016; verify output file created | `requirements-findings.md` exists, non-empty, has defined header |
| FR-3 Completeness | Eval (fixture) | Ticket with a problem statement that has no FR | Output contains "COMPLETENESS" label |
| FR-3 Testability | Eval (fixture) | AC stated as "should feel responsive" (no measurable threshold) | Output contains "TESTABILITY" label and "measurable" or "threshold" in description |
| FR-3 Coverage | Eval (fixture) | Success criterion from problem.md absent from all ACs | Output contains "COVERAGE" label |
| FR-3 Consistency | Eval (fixture) | FR-1 says "must X", FR-2 says "must never X" | Output contains "CONSISTENCY" label and references both FR numbers |
| FR-3 Adversarial | Eval (fixture) | requirements.md contains injection-like phrase ("ignore previous instructions") | Output contains no unrelated tool calls or non-findings content |
| FR-6 (clean report) | Eval (fixture) | Well-formed ticket with no defects | Output contains exact phrase "No findings" |
| FR-9 (missing requirements.md) | Integration | Ticket dir exists but requirements.md absent | Error message in response; no `requirements-findings.md` created |
| FR-7 (read-only) | Integration | Hash problem.md and requirements.md before + after invocation | Hashes unchanged |
| Path containment | Integration | Pass `"0016/../../../etc"` as ticket number | Error message; no file reads outside `.tickets/` |
| FR-2 | — | xref requirements.md FR-2 |
| FR-4 | — | xref requirements.md FR-4 |
| FR-5 | — | xref requirements.md FR-5 |
| FR-8 | — | xref requirements.md FR-8 |

## Tradeoffs

- **Chose read-only subagent over inline analysis**: Scopes the prompt-injection attack surface by restricting the analysis context to Read/Grep/Glob only; the parent skill (which has file-write access) receives findings text and writes the output. Extra context-boot cost is accepted in exchange for fail-closed security posture.
- **Accepting risk of false negatives on Consistency**: LLM-driven contradiction detection is best-effort. Mitigation: SKILL.md instructs the subagent to compare each FR pair, not just adjacent ones; the output report footer includes a caveat that Consistency detection may miss subtle contradictions so operators are not silently misled.
- **Persistent fixtures over ephemeral**: Fixture directories committed permanently at `skills/requirements-review/fixtures/` provide regression safety for future prompt changes. Small storage cost accepted.

## Risks

- Hallucinated findings — the skill might flag a false positive on Testability for an AC that is genuinely binary. Mitigation: the Testability dimension definition requires a concrete reason (e.g., "no measurable threshold given") rather than just flagging subjective language.
- Ticket slug resolution returns a stale or renamed directory. Mitigation: resolver validates the resolved path is a direct child of `.tickets/` and that both required files exist before any analysis begins (FR-9 guard).
- Multiple directories match the same four-digit prefix (race or manual artifact). Mitigation: resolver halts with an error listing ambiguous candidates rather than silently picking one.
- Completeness and Coverage findings may both fire for the same problem-statement gap (a missing FR also implies a missing AC). This double-flagging is intentional and more useful than silence; the Consistency caveat footer in the output report will note that overlapping findings across dimensions are expected and not errors.

## Implementation Order

1. Create `skills/requirements-review/fixtures/` with five fixture ticket directories: `completeness-defect/`, `testability-defect/`, `coverage-defect/`, `consistency-defect/`, `clean/` — each with a `problem.md` and `requirements.md` that exhibit the named defect (or none).
2. Create `skills/requirements-review/SKILL.md` with: frontmatter, ticket resolver with path containment check, guard clause for missing artifacts, read-only subagent dispatch with four dimension definitions and output schema, parent writes output file, and report footer with Consistency caveat.
3. Verify each fixture by invoking the skill against it and confirming the oracle criteria from the test plan are met.
4. Verify end-to-end on ticket 0016 itself.
5. Add `requirements-review` to the skill catalog in `README.md` (skills table) after end-to-end verification passes.
