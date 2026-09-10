# Requirements

**Ticket**: 0081
**Title**: Parallelize multi-panel design-review critic rounds

## Functional Requirements

1. `/problem` Phase 5 must run `panel_detect.py` itself, in-session, before
   spawning any critic agent — `--root` the project root, `--design`, and
   the file list inferred from solution.md's intended changes — to obtain
   `active`/`candidates`/`skipped`, and must disposition every `candidates`
   entry itself (activate or defer, one-line reason).
2. Every spawned agent, in either branch below, must receive the fully
   resolved active-panel list via a new `Panels:` field — no code path
   must leave an agent to independently re-run its own panel detection.
3. If the resolved non-Core panel count is fewer than 2, Phase 5 must spawn
   exactly one critic agent with `Panels: <every active panel,
   comma-joined>` — functionally equivalent to today (same total review
   depth and content), the only difference being the agent receives the
   pre-resolved list instead of re-deriving it itself.
4. If the resolved non-Core panel count is 2 or more, Phase 5 must spawn
   one critic agent per active panel, as parallel Agent tool calls in a
   single message: the agent assigned `Panels: Core` also receives
   problem.md's 5 design-specific evaluations; every other agent's
   `Panels:` value names exactly its one panel and receives no added
   evaluations.
5. `critic-brief.md` Step 1 must gain an optional `Panels: <name>[,
   <name>...]` field: when present, the agent must skip its own
   `panel_detect.py` invocation, treat the given names as the fixed and
   complete active set, and must not additionally self-activate or
   disposition any other candidate panel — a `Panels:`-scoped agent reviews
   only the named panel(s), full stop. When absent, Step 1 is unchanged.
6. Before merging, Phase 5 must verify, per spawned agent: (a) a report was
   actually returned (not missing, errored, or timed out), and (b) the
   agent's own "active panels" announcement names exactly its assigned
   `Panels:` value, no more and no fewer. Any missing report or
   panel-label mismatch must halt the round and report the failure to the
   lead — it must never be silently merged as if complete.
7. The merge is concatenation of every verified report into one findings
   document, under one header naming every contributing panel once; no
   fuzzy dedup logic. Content overlap between Core's broad dimensions and
   a specific panel's specialized dimension (e.g. both independently
   flagging the same injection hazard at the same location) is an
   accepted, undeduped tradeoff — the no-duplication guarantee is that no
   two agents redo work within the *same* assigned panel, not that two
   different panels can never describe the same location.
8. If a second round is reached, Phase 5 must re-run panel detection fresh
   against the revised solution.md rather than reusing round 1's resolved
   set. If round 2's fan-out decision (agent count or assignment) differs
   from round 1's, Phase 5 must state that difference in one line before
   spawning round 2's agents.
9. The 2-round Checkpoint-1 budget stays 2 total revision passes; a pass
   possibly fans out per FR-3/FR-4, but that never counts as more than one
   round.
10. Secondary-panel escalation must never be automatically triggered by the
    fan-out; both files must document it as an orchestrator-optional
    manual step, exercised only after reading the merged reports.

## Non-Functional Requirements

1. `critic-brief.md`'s existing severity vocabulary, anti-patterns, and
   Step 1 no-`Panels:`-field behavior are unchanged — this is additive.
2. Parallel agent spawns must be issued as multiple Agent tool calls in one
   message (the harness's own parallel-tool-call convention), never
   sequential calls that defeat the wall-clock benefit.

## Test Strategy

| Type       | Rationale                                                            |
|------------|-------------------------------------------------------------------------|
| Doc-wiring | `critic-brief.md` documents the optional `Panels:` field, its skip-detection behavior, and the no-self-activation constraint |
| Doc-wiring | Phase 5 documents in-session detection + candidate disposition, and that every spawned agent (both branches) receives a `Panels:` field |
| Doc-wiring | Phase 5 documents the fan-out threshold, the Core agent's added evaluations, and non-Core agents receiving none |
| Doc-wiring | Phase 5 documents the per-agent report-verification step (presence + panel-label match) before merging, and the halt-on-mismatch behavior |
| Doc-wiring | Phase 5 documents concatenation-only merge, the accepted cross-panel content-overlap tradeoff, and the contributing-panels header |
| Doc-wiring | Phase 5 documents round-2 fresh re-detection and surfacing a changed fan-out decision |
| Doc-wiring | Both files document Secondary-panel escalation as manual-only |

## Acceptance Criteria

- A design review with fewer than 2 non-Core panels active spawns exactly
  one critic agent, given the pre-resolved `Panels:` list.
- A design review with 2 or more non-Core panels active spawns one agent
  per panel, in parallel, each agent's `Panels:` value naming only its own
  assigned panel(s); the Core agent alone also carries the 5 design-specific
  evaluations.
- Phase 5 verifies every spawned agent's report is present and its
  announced panels match its assignment before merging; a missing or
  mismatched report halts the round rather than merging silently.
- The merged findings document names every contributing panel once and
  preserves every finding's exact header-line format.
- Round budget stays at 2 total revision passes regardless of fan-out size
  in either pass; a changed fan-out between rounds is surfaced, not silent.

## Open Questions

None.
