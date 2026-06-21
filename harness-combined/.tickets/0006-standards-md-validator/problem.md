# Problem Statement

**Ticket**: 0006
**Title**: _standards.md schema validator
**Date**: 2026-06-21

## Problem

When a harness operator runs `/init`, a `_standards.md` stub is created with placeholder sections but never enforced to be filled in. Downstream commands `/problem` and `/build` silently proceed with blank or stub engineering standards, meaning specs are generated without real language, test strategy, or tooling constraints. There is no early-warning mechanism that catches an unfilled `_standards.md` before expensive pipeline work runs.

## Impact

- Harness operator's generated specs carry no engineering standards, producing output that ignores project conventions.
- Errors are silent: no failure or warning fires; the operator only discovers the gap when reviewing low-quality output.
- Repeated runs compound the problem — the operator may iterate through several spec/build cycles before realizing the root cause.

## Success Criteria

- A validator runs early in `/problem` and `/build` (before any generative work begins).
- The validator detects: missing required sections, sections present but containing only stub/placeholder text.
- On failure, a clear, actionable error message lists which sections are missing or still stubbed — then stops.
- On success (all required sections populated with real content), the validator passes silently.
- The required sections checked are at minimum: language, test strategy.

## Out of Scope

- Auto-filling or suggesting content for missing sections.
- Validating the quality or correctness of the standards content beyond stub detection.
- Validating optional/custom sections the operator has added.
