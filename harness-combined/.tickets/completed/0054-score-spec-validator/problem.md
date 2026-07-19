# Problem Statement

**Ticket**: 0054
**Title**: Score-spec Python validator: mechanical checks 1-6
**Date**: 2026-07-12

## Problem

Score-spec checks 1-6 (`context/score-spec.md`) are mechanical — regex-decidable —
yet every consumer (/problem Phase 6, /write-spec, /build, autopilot Step S)
re-applies them by model re-reading of the prose spec. That burns context and
drifts across runs, undermining the BLOCK gate's authority.

## Impact

- Ticket authors get inconsistent PASS/WARN/BLOCK verdicts for the same artifacts.
- Autopilot Step S classifies remediation off model-reported check names; a
  misapplied check misroutes mechanical vs semantic repair.
- Every scoring pass spends model tokens on work a script does deterministically.

## Success Criteria

- `validators/score_spec.py` implements checks 1-6 deterministically (stdlib only),
  matching `context/score-spec.md` semantics including severity (BLOCK: FR count,
  imperative language, test-plan coverage, no placeholders; WARN: implementation
  order, acceptance criteria).
- CLI prints the standard report block (check lines + verdict) and exits non-zero
  on BLOCK, mirroring the `standards_validator.py` convention.
- Check 7 (FR testability) remains model-judged: the validator never emits it;
  consumer prose composes it into the report after the mechanical lines.
- Unit tests cover each check's pass/fail plus placeholder edge cases (fenced code
  blocks, single-token brackets, stub table cells).
- `context/score-spec.md` directs consumers to run the validator for checks 1-6
  and judge only check 7 — wiring all consumers via the one doc they already read.

## Out of Scope

- Changing check semantics or severities defined in `context/score-spec.md`.
- Rewiring `gates/spec_remediate.py` remediation logic (it may be reused, not changed).
- Editing individual command/flow files (they delegate to score-spec.md already).
