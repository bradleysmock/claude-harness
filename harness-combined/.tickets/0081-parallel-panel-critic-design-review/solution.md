# Solution

**Ticket**: 0081
**Title**: Parallelize multi-panel design-review critic rounds

## Approach

Move panel detection out of the critic subagent and into `/problem` Phase 5
itself (already-deterministic Python, `panel_detect.py`), so the
orchestrator knows the full active-panel set *before* deciding how many
agents to spawn. Add one optional field to `critic-brief.md`'s brief,
`Panels: <name>[, <name>...]`, that lets the orchestrator hand a critic
agent a pre-resolved, fixed panel assignment instead of having it run its
own detection. Below the 2-non-Core-panel threshold, spawn exactly one
agent exactly as today (the field is simply omitted). At or above it, spawn
one agent per panel in parallel and concatenate their structured reports —
no fuzzy merge needed, since panel assignment makes the finding-spaces
disjoint by construction.

## Components

| Component | Responsibility |
|---|---|
| `context/critic-brief.md` Step 1 | Additive `Panels:` field: when present, skip the script call, use the given fixed set |
| `commands/problem.md` Phase 5 | Run `panel_detect.py` in-session; disposition `candidates`; branch single-vs-parallel spawn; concatenate reports |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Orchestrator runs `panel_detect.py` directly, not inside the critic | The orchestrator must know the panel count *before* spawning to decide fan-out — deterministic Python, matches the LLM/Python boundary rule |
| Concatenation merge, no dedup logic | Panel assignment (one panel per agent, Core owns cross-cutting evals) makes finding-spaces disjoint by construction — a fuzzy merge would be solving a problem this partition doesn't create |
| New `Panels:` field is additive/optional | Its absence leaves every existing single-agent call site (this ticket's own code-review path, `build-ticket.md` Step 7) byte-identical — no regression risk from a field they never set |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|--------------|
| FR-1/FR-2   | Doc-wiring  | Phase 5 documents the in-session `panel_detect.py` run and candidate disposition |
| FR-3        | Doc-wiring  | Phase 5 documents the single-agent fallback below the 2-non-Core-panel threshold, unchanged brief |
| FR-4        | Doc-wiring  | Phase 5 documents the per-panel parallel spawn, Core's added evaluations, other panels' no-added-evaluations |
| FR-5        | Doc-wiring  | `critic-brief.md` Step 1 documents the optional `Panels:` field additively, skip-detection behavior |
| FR-6        | Doc-wiring  | Phase 5 documents concatenation-only merge, no dedup logic, format preserved |
| FR-7        | Doc-wiring  | Phase 5 states the 2-round budget is per-pass, not per-panel |
| FR-8        | Doc-wiring  | Both files state Secondary-panel escalation stays manual |

## Tradeoffs

- **Chose a 2-non-Core-panel threshold over always splitting because**:
  splitting Core+1 into two agents trades a small wall-clock win for
  spawn/read/merge overhead that isn't clearly worth it below that count —
  tunable later if real usage says otherwise.
- **Accepting risk of**: more total tokens spent (each panel-agent reads
  the same design docs independently) in exchange for wall-clock speed —
  acceptable since Checkpoint 1 latency is the pain point, not token spend.

## Risks

- A panel-agent given a fixed `Panels:` set could still be tempted to
  additionally judge `candidates` itself if not explicitly told not to —
  mitigate by stating in `critic-brief.md`'s new field text that a
  `Panels:`-scoped agent reviews *only* the named panel(s), full stop.
- Losing the single-critic's own "Announce which panels are active" framing
  across split reports — mitigate by having the orchestrator's merge
  header name every contributing panel once, at the top of the concatenated
  document.

## Implementation Order

1. Doc-wiring tests for both files — red first.
2. `context/critic-brief.md`: add the additive `Panels:` field to Step 1.
3. `commands/problem.md` Phase 5: add in-session panel detection, the
   threshold branch, the parallel spawn instructions, and the merge step.
4. Confirm tests green; confirm no existing Phase 5 / critic-brief.md
   content removed or reworded outside the additive sections.
