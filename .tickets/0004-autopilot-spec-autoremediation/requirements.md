# Requirements

**Ticket**: 0004
**Title**: Autopilot auto-remediates score-spec BLOCKs instead of bailing

## Functional Requirements

1. On a BLOCK verdict at the autopilot score-spec gate, the system must enter a
   spec auto-remediation step instead of halting back to the lead.
2. The system must classify each failing BLOCK check as *mechanical*
   (deterministically fixable from existing text) or *semantic* (needs judgment).
3. Test-plan coverage must be fixed *structurally only*: append a row keyed to the
   uncovered FR number with the scenario cell cross-referencing that FR's existing
   text (no synthesized prose); remove any phantom row (FR absent from requirements).
4. Imperative-language must be fixed by literal token substitution: a flagged FR's
   `should`/`may`/`could` becomes `must`, with no other rewording.
5. FR-count and placeholder (`<...>` prose, `TODO`/`TBD`/`FIXME`) failures must be
   routed to `/refine` running in a new non-interactive autopilot mode: single
   pass, fix only the flagged checks, derive content only from existing artifact
   text, surface no Open Questions / next-command prompts, and bail if undrivable.
6. The classifier must parse score-spec's fixed check lines; any check in BLOCK
   state whose name is not in the recipe table must fall through to hard-stop
   (fail closed). This is a defense-in-depth guard for future score-spec checks.
7. After any fix, the system must commit the revised artifacts to `main` and
   re-run score-spec against the committed files; the re-score is authoritative.
8. The loop must be bounded to ≤1 mechanical pass + ≤1 refine pass; if still BLOCK
   after the budget, the system must hard-stop (show residual checks, return to lead).
9. A ticket cleared by mechanical fixes only must stay fully autonomous; one that
   required a semantic `/refine` pass must reach build but must not silently
   auto-deliver — it must surface at the post-build diff (Step B) for confirmation.
10. Auto-remediation must apply only in autopilot mode; interactive `/build` and
    `/write-spec` must retain hard-stop-on-BLOCK, with hard-stop as the default
    when autopilot mode is not in effect.

## Non-Functional Requirements

1. No worktree may be created until the verdict is PASS/WARN (preserve the "fix
   before worktree" invariant); every mechanical edit must be announced in one
   line for lead audit.

## Test Strategy

| Type        | Rationale                                                   |
|-------------|-------------------------------------------------------------|
| Unit        | Score-spec gate re-scores correctly after a synthetic fix.  |
| Integration | Autopilot flow: BLOCK → remediate → re-score → continue/bail.|

## Acceptance Criteria

- A missing-Test-Plan-row ticket builds under autopilot with no lead intervention;
  the structural row is added and committed.
- A `<...>`-placeholder ticket triggers non-interactive `/refine`, then surfaces at
  Step B for confirmation (no silent merge).
- A fix that clears check A but surfaces a new BLOCK on B is bounded (bails after
  budget), not looped; an FR-count BLOCK `/refine` can't resolve bails, not fabricates.
- Interactive `/build` on a BLOCK ticket still hard-stops as before.

## Open Questions

- None. FR-count resolved: `/refine` derives a missing FR only from existing text, else bails; net-new scope disallowed.
