# Solution

**Ticket**: 0081
**Title**: Parallelize multi-panel design-review critic rounds

## Approach

Move panel detection out of the critic subagent and into `/problem` Phase 5
itself (already-deterministic Python, `panel_detect.py`), so the
orchestrator resolves the full active-panel list *before* deciding how
many agents to spawn — and passes that same resolved list to *every*
spawned agent via one new `critic-brief.md` field, `Panels:
<name>[, <name>...]`, so no agent (single or parallel) ever re-derives it
independently. Below the 2-non-Core-panel threshold, spawn one agent
carrying the full list (same total review depth as today, just
pre-resolved). At or above it, spawn one agent per panel in parallel,
verify every report actually arrived and stayed inside its assigned
panel(s), then concatenate — no fuzzy merge, because panel assignment is
enforced explicitly (Step 1's new constraint), not assumed.

## Components

| Component | Responsibility |
|---|---|
| `context/critic-brief.md` Step 1 | Additive `Panels:` field: skip self-detection, use the given fixed set, never self-activate another panel |
| `commands/problem.md` Phase 5 | Run `panel_detect.py` in-session; disposition `candidates`; always pass `Panels:` to every spawn; branch single-vs-parallel; verify each report before merging |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Every agent gets `Panels:`, not just the parallel branch | Removes the single-agent path's silent re-detection gap (round 1 critic finding: it could legitimately diverge from Phase 5's own threshold decision) |
| Core's agent gets `Panels: Core` explicitly in the fan-out branch | Without it, an unconstrained Core agent could self-activate a panel already assigned elsewhere, breaking the partition (round 1 critic BLOCKER) |
| Verify presence + panel-label match before merging | A missing or overreaching agent report must halt the round, not silently merge as complete (round 1 critic BLOCKER) — cheap because Step 1 already requires an "active panels" announcement line to check against |
| Concatenation, accepted content-overlap tradeoff | Core's broad security/quality dimensions can legitimately restate a panel-specific finding at the same location; declared as an accepted redundancy rather than a false disjointness claim (round 1 critic MAJOR) |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|--------------|
| FR-1        | Doc-wiring  | Phase 5 documents the in-session `panel_detect.py` run and candidate disposition |
| FR-2/FR-3   | Doc-wiring  | Phase 5 documents every spawn (single or parallel) receiving a `Panels:` field |
| FR-4        | Doc-wiring  | Phase 5 documents the fan-out threshold, Core's added evaluations, others' none |
| FR-5        | Doc-wiring  | `critic-brief.md` documents the field, skip-detection, and no-self-activation constraint |
| FR-6        | Doc-wiring  | Phase 5 documents the presence + panel-label verification and halt-on-mismatch |
| FR-7        | Doc-wiring  | Phase 5 documents concatenation-only merge, the overlap tradeoff, contributing-panels header |
| FR-8/FR-9   | Doc-wiring  | Phase 5 documents round-2 fresh re-detection, surfacing a changed fan-out, and that a fan-out never counts as more than one round |
| FR-10       | Doc-wiring  | Both files document Secondary-panel escalation as manual-only |

## Tradeoffs

- **Chose explicit per-agent panel constraints over trusting disjointness
  by convention because**: round 1's critic review showed an unconstrained
  agent can drift (self-activate, re-detect) — an explicit `Panels:` field
  plus a verification step is cheap and closes that gap directly.
- **Chose to declare Core/panel content overlap as accepted, not fixed,
  because**: this ticket is explicitly out of scope for changing panel
  content, and the alternative (a fuzzy cross-panel dedup) trades a small
  reviewer redundancy for real merge complexity.
- **Accepting risk of**: more total tokens spent (independent reads per
  agent) in exchange for wall-clock speed — unchanged from the original
  tradeoff, still judged worth it since Checkpoint 1 latency is the pain
  point.

## Risks

- A `Panels:`-scoped agent could still, despite the instruction, judge and
  report on an out-of-scope panel — mitigated by FR-6's verification step,
  not by trusting the instruction alone.
- Round-2 re-detection changing the fan-out from round 1 could surprise
  the lead if unstated — mitigated by FR-8's explicit one-line surfacing.

## Implementation Order

1. Doc-wiring tests for both files — red first.
2. `context/critic-brief.md`: add the additive `Panels:` field, its
   skip-detection behavior, and the no-self-activation constraint to Step 1.
3. `commands/problem.md` Phase 5: in-session detection, always-pass-`Panels:`,
   the threshold branch, per-agent verification, concatenation merge, and
   round-2 fresh re-detection.
4. Confirm tests green; confirm no existing Phase 5 / critic-brief.md
   content removed or reworded outside the additive sections.
