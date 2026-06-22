# Requirements

**Ticket**: 0016
**Title**: Requirements integrity review skill

## Functional Requirements

1. The system must provide a `/requirements-review XXXX` skill invocable by the harness operator on any ticket in `requirements` or `solution` status (i.e., whose `.tickets/XXXX-<slug>/` directory contains both `problem.md` and `requirements.md`).
2. The system must read `problem.md` and `requirements.md` for the specified ticket before producing any output.
3. The system must evaluate requirements across four named dimensions:
   - **Completeness** — every problem claim and impact item in `problem.md` maps to at least one FR in `requirements.md`. (Example defect: problem states "X fails silently" but no FR addresses silent failure handling.)
   - **Testability** — every AC is binary pass/fail verifiable with a measurable threshold. (Example defect: AC says "should feel responsive" with no latency target.)
   - **Coverage** — every success criterion from `problem.md` § Success Criteria is addressed by at least one AC in `requirements.md`. (Example defect: success criterion "a clean ticket produces a short no-findings summary" has no corresponding AC.)
   - **Consistency** — no FR contradicts another FR, and no AC contradicts its corresponding FR. (Example defect: FR-1 states "the system must X", FR-4 states "the system must never X".)
4. The system must write findings to `.tickets/XXXX-<slug>/requirements-findings.md`.
5. Each finding must include: dimension name, description of the defect, and a concrete fix suggestion.
6. When no findings are identified across all four dimensions, the report must state "No findings — requirements are complete, testable, covered, and consistent."
7. The skill must not modify `problem.md` or `requirements.md`.
8. The skill must resolve the ticket slug from the ticket number — the operator passes only the four-digit number, not the full slug.
9. If the specified ticket number does not exist or is missing `problem.md` or `requirements.md`, the skill must stop and report the missing artifact with a clear message.

## Non-Functional Requirements

1. The skill must complete its analysis and write the report within a single session invocation (no background agents or async steps beyond the scoped read-only analysis subagent).
2. Each finding in the report must not exceed 5 lines (dimension label, description, fix suggestion). There is no cap on the number of findings.
3. The skill must be read-only with respect to all harness artifacts other than the `requirements-findings.md` output file.
4. The analysis subagent must be restricted to Read, Grep, and Glob tools only — no file-write tools in the analysis context.

## Test Strategy

| Type        | Rationale                                             |
|-------------|-------------------------------------------------------|
| Unit        | Each dimension's detection logic against fixture ticket dirs with known defects |
| Integration | End-to-end invocation against a real ticket with seeded problems; verify findings file written and correct |

## Acceptance Criteria

- Invoking `/requirements-review 0016` on this ticket produces a `requirements-findings.md` file in the ticket directory.
- A ticket with an AC stated as "the system should feel responsive" is flagged under Testability.
- A ticket where problem.md lists a success criterion absent from all ACs is flagged under Coverage.
- A ticket where FR-1 states "the system must X" and FR-2 states "the system must never X" is flagged under Consistency.
- A ticket where a problem statement has no corresponding FR is flagged under Completeness.
- A ticket with well-formed requirements produces a "No findings" report, not an empty file.
- Running the skill on a ticket whose `requirements.md` is missing produces an error message, no partial findings file.
- The skill does not alter `problem.md` or `requirements.md` after invocation.

## Open Questions

- None.
