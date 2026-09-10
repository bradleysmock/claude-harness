# Spec Coverage Map

**Ticket**: 0081-parallel-panel-critic-design-review
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | `/problem` Phase 5 must run `panel_detect.py` itself, in-session, | — |
| FR-2 | FR | Every spawned agent, in either branch below, must receive the fully | — |
| FR-3 | FR | If the resolved non-Core panel count is fewer than 2, Phase 5 must spawn | — |
| FR-4 | FR | If the resolved non-Core panel count is 2 or more, Phase 5 must spawn | — |
| FR-5 | FR | `critic-brief.md` Step 1 must gain an optional `Panels: <name>[, | — |
| FR-6 | FR | `critic-brief.md` Step 1 must define one exact literal format for the | — |
| FR-7 | FR | Before merging, Phase 5 must verify, per spawned agent: (a) a report was | — |
| FR-8 | FR | The merge is concatenation of every verified report into one findings | — |
| FR-9 | FR | If a second round is reached, Phase 5 must re-run panel detection fresh | — |
| FR-10 | FR | The 2-round Checkpoint-1 budget stays 2 total revision passes; a pass | — |
| FR-11 | FR | Secondary-panel escalation must never be automatically triggered by the | — |
| AC-1 | AC | A design review with fewer than 2 non-Core panels active spawns exactly | — |
| AC-2 | AC | A design review with 2 or more non-Core panels active spawns one agent | — |
| AC-3 | AC | Every agent's report uses the exact `Panels active: <list>` format; | — |
| AC-4 | AC | The merged findings document names every contributing panel once and | — |
| AC-5 | AC | Round budget stays at 2 total revision passes regardless of fan-out size | — |

## Uncovered

- FR-1 (FR): `/problem` Phase 5 must run `panel_detect.py` itself, in-session,
- FR-2 (FR): Every spawned agent, in either branch below, must receive the fully
- FR-3 (FR): If the resolved non-Core panel count is fewer than 2, Phase 5 must spawn
- FR-4 (FR): If the resolved non-Core panel count is 2 or more, Phase 5 must spawn
- FR-5 (FR): `critic-brief.md` Step 1 must gain an optional `Panels: <name>[,
- FR-6 (FR): `critic-brief.md` Step 1 must define one exact literal format for the
- FR-7 (FR): Before merging, Phase 5 must verify, per spawned agent: (a) a report was
- FR-8 (FR): The merge is concatenation of every verified report into one findings
- FR-9 (FR): If a second round is reached, Phase 5 must re-run panel detection fresh
- FR-10 (FR): The 2-round Checkpoint-1 budget stays 2 total revision passes; a pass
- FR-11 (FR): Secondary-panel escalation must never be automatically triggered by the
- AC-1 (AC): A design review with fewer than 2 non-Core panels active spawns exactly
- AC-2 (AC): A design review with 2 or more non-Core panels active spawns one agent
- AC-3 (AC): Every agent's report uses the exact `Panels active: <list>` format;
- AC-4 (AC): The merged findings document names every contributing panel once and
- AC-5 (AC): Round budget stays at 2 total revision passes regardless of fan-out size
