# Problem Statement

**Ticket**: FIXTURE
**Title**: Report generation (coverage-defect fixture)

## Problem

The reporter emits an empty file when there is nothing to report, confusing operators.

## Impact

- An empty output file is indistinguishable from a crash.

## Success Criteria

- A run with data produces a populated report.
- A clean run with no data produces a short no-findings summary rather than an empty file.

## Out of Scope

- Report styling.
