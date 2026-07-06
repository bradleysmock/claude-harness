# Problem Statement

**Ticket**: 0014
**Title**: Spec Coverage Map
**Date**: 2026-06-21

## Problem

After `/write-spec` generates specs for a ticket, there is no automated check that every functional requirement (FR) and acceptance criterion (AC) from `requirements.md` has at least one corresponding test spec. The gap between requirements and specs is invisible until `/build` runs — or worse, until a reviewer notices missing coverage post-implementation. There is no artifact tying requirements to the specs that cover them.

## Impact

- Harness operators (lead engineers) may begin `/build` with uncovered FRs or ACs, leading to implementation without test backing.
- Missing coverage is discovered late (post-implementation review) rather than early (pre-build gate).
- Requirements drift: specs accumulate over iterations with no record of which requirement motivated which spec.

## Success Criteria

- After `/write-spec` runs, a `spec-coverage.md` file is written to `.tickets/XXXX-<slug>/` linking each FR and AC to the spec(s) covering it.
- FRs and ACs with no covering spec are flagged as warnings in the coverage map.
- `/build` checks for uncovered requirements and surfaces a warning (non-blocking) before proceeding.
- Coverage map is human-readable and auditable by the lead before approving the build.

## Out of Scope

- Automatic spec generation to fill coverage gaps (lead decides what specs to add).
- Code-level test coverage (line/branch coverage) — this is spec-to-requirement traceability only.
- Coverage enforcement as a hard gate blocking `/build` (warning only; lead retains authority to proceed).
- Retroactive coverage maps for tickets that predate this feature.
