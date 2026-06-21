# Requirements

**Ticket**: 0006
**Title**: _standards.md schema validator

## Functional Requirements

1. The system must check for the existence of `.tickets/_standards.md` at the start of `/problem` and `/build` pipeline execution, before any generative phase runs.
2. The system must verify that each required section heading (at minimum: `language`, `test strategy`) is present in `_standards.md`.
3. The system must detect stub/placeholder content — defined as a section whose body matches a known stub pattern (e.g. `TODO`, `<fill in>`, `placeholder`, empty after the heading, or identical to the `/init`-generated default text).
4. The system must halt pipeline execution and emit a structured error when any required section is missing or contains stub content.
5. The error message must enumerate each failing section by name and state the reason (missing vs. stubbed).
6. The system must pass silently (no output, no interruption) when all required sections are populated with non-stub content.
7. The required section list must be configurable so operators can extend it without modifying harness internals.

## Non-Functional Requirements

1. The validator must add no perceptible latency to pipeline startup (target: < 50 ms on any reasonable `_standards.md` size).
2. The validator must not write to any file or produce side effects on success.
3. Stub-pattern matching must be case-insensitive and must not produce false positives on legitimate short content (e.g. a one-word language declaration like "Python" is valid).

## Test Strategy

| Type        | Rationale                                                             |
|-------------|-----------------------------------------------------------------------|
| Unit        | Validator logic: section detection, stub matching, error formatting   |
| Integration | End-to-end: `/problem` and `/build` fail fast when `_standards.md` is stub; pass when populated |

## Acceptance Criteria

- Running `/problem` or `/build` with a stub `_standards.md` (as produced by `/init` with no edits) halts before Phase 0 completes and prints a section-by-section error list.
- Running `/problem` or `/build` with a fully populated `_standards.md` proceeds without any validator output.
- A `_standards.md` missing the `language` section triggers a "missing section" error for `language`.
- A `_standards.md` where `test strategy` section contains only `TODO` triggers a "stub content" error for `test strategy`.
- The required section list can be extended by editing a single config location without modifying validator code.

## Open Questions

- None.
