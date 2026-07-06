# Requirements

**Ticket**: 0014
**Title**: Spec Coverage Map

## Functional Requirements

1. The system must parse `requirements.md` for a ticket and extract all Functional Requirements (numbered items under `## Functional Requirements`) and Acceptance Criteria (bullet items under `## Acceptance Criteria`).
2. The system must parse spec files at `.harness/specs/XXXX-<slug>-*.py` and extract the `acceptance_criteria` list from each `Spec(...)` definition.
3. The system must match each extracted FR and AC from `requirements.md` to zero or more specs using text-similarity matching (substring or normalized token overlap).
4. The system must write a `spec-coverage.md` file to `.tickets/XXXX-<slug>/` after `/write-spec` runs, containing a table mapping each FR/AC to the spec(s) covering it, plus an "Uncovered" section listing all FRs and ACs with no matching spec.
5. The system must emit a visible warning (non-blocking) at the start of `/build` if `spec-coverage.md` contains any uncovered FRs or ACs — listing the uncovered items — before proceeding with the build.
6. The coverage map must be regenerated (overwritten) each time `/write-spec XXXX` runs, so it reflects the current spec state.

## Non-Functional Requirements

1. Coverage map generation must complete in under 2 seconds for tickets with up to 20 FRs/ACs and 10 specs.
2. The `spec-coverage.md` format must be human-readable Markdown with a table and clearly labeled uncovered section.
3. Matching must be case-insensitive and strip punctuation to reduce false negatives from minor wording differences.

## Test Strategy

| Type        | Rationale                                                                 |
|-------------|---------------------------------------------------------------------------|
| Unit        | Parser functions for FRs/ACs and spec `acceptance_criteria` extraction    |
| Unit        | Matching logic: covered vs. uncovered classification                      |
| Integration | Full flow: given sample `requirements.md` + spec files → verify `spec-coverage.md` content |
| Integration | `/build` warning emission when uncovered items exist in `spec-coverage.md` |

## Acceptance Criteria

- Given a ticket with 3 FRs and 2 ACs where 2 FRs and 1 AC have matching specs, `spec-coverage.md` lists 1 FR and 1 AC as uncovered.
- Given a ticket where all FRs and ACs have matching specs, `spec-coverage.md` contains no uncovered items and the "Uncovered" section states "None."
- `/write-spec XXXX` always writes or overwrites `spec-coverage.md` as its final step.
- `/build XXXX` prints a warning listing uncovered items if any exist in `spec-coverage.md` before proceeding; no warning is shown when all items are covered.
- The coverage map table includes columns: Requirement ID, Requirement Text, Covering Spec(s).
- The feature has no effect on tickets that have no `spec-coverage.md` (backward-compatible; `/build` skips the check silently if the file does not exist).

## Open Questions

- None.
