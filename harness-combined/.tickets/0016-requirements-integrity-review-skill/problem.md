# Problem Statement

**Ticket**: 0016
**Title**: Requirements integrity review skill
**Date**: 2026-06-21

## Problem

The harness has no targeted checkpoint between `/problem` and `/build` that validates requirements quality. The general critic evaluates design holistically but does not deeply interrogate whether requirements.md is internally consistent, fully covers the problem, and is expressed in a testable form. Defects in requirements (missing coverage, untestable ACs, contradictions) propagate into specs and tests, causing rework discovered late — after implementation is already underway.

## Impact

- Harness operators (lead engineers) discover requirements gaps during `/build` or post-build review rather than before specs are written.
- Untestable ACs produce weak gate suites that pass but don't verify the correct behavior.
- Contradictions between FRs yield conflicting implementations that survive the critic because no reviewer held requirements.md up against problem.md line-by-line.

## Success Criteria

- A `/requirements-review XXXX` skill exists and can be invoked on any ticket in `requirements` or `solution` status (both `problem.md` and `requirements.md` must exist).
- The skill reads problem.md and requirements.md for the given ticket and produces a structured findings report.
- Findings cover four named dimensions: completeness, testability, coverage, consistency.
- The report is written to `.tickets/XXXX-<slug>/requirements-findings.md` (distinct from gate-findings.md).
- Each finding includes: dimension, description, and a concrete fix suggestion.
- A clean ticket (no issues) produces a short "no findings" summary rather than an empty file.
- The skill does not modify problem.md or requirements.md — read-only, advisory output only.

## Out of Scope

- Auto-rewriting requirements.md based on findings (that is a future `/requirements-repair` capability).
- Integration with the gate engine or CI pipeline.
- Reviewing solution.md (the skill focuses only on requirements quality, not solution design).
