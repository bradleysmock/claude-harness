# Solution

**Ticket**: 0074
**Title**: Data-driven promotion policy

## Approach

Add `gates/policy.py`: two frozen dataclasses (`PolicyRule`,
`PromotionVerdict`) and two pure functions, `load_policy` and
`evaluate_promotion`. `commands/gate.md` and the build repair loop call
`evaluate_promotion` instead of each re-deriving pass/fail logic inline.
Gate *execution* and scheduling are untouched — this only centralizes the
verdict → promote/block/pause decision.

## Components

| Component | Responsibility | Key interface |
|---|---|---|
| `gates/policy.py` | Policy model + pure evaluator | `load_policy(text)`, `evaluate_promotion(results, policy)` |
| `gates/config.py` | Parse `[policy]` sub-block inside `[gates]` fence | reuses existing fenced-block parser |
| `commands/gate.md` | Render outcome/reasons instead of inline boolean | calls `evaluate_promotion` |
| `context/flows/build-ticket.md`, `repair-escalation.md` | Route `pause_for_human` through existing escalation halt | reads `PromotionVerdict.outcome` |
| `context/harness-reference.md` | Documents policy table + escalation reuse | — |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Pure function, dataclasses in/out | Matches `repair_integrity.py`'s diff classifier — unit-testable without filesystem or subprocess |
| `[policy]` nested in existing `[gates]` fence | Reuses `gates/config.py`'s fail-closed fenced-block parser instead of a new file format |
| No new ticket status for pause | `repair-escalation.md`/`autopilot-ticket.md` already halt-and-hand-to-lead on exhausted repair; reuse that shape (see Decisions) |
| Default policy = today's behavior | Every override in `_standards.md` is additive-by-default (same guarantee as `ticket_templates.py`) |

## Decisions (resolves source doc's Checkpoint-1 questions)

- **Pause routing**: always route through the exhausted-escalation shape,
  even on a gate's *first* failure. A lighter-weight "pause without prior
  repair attempts" variant is deferred — introducing it now would add a
  second halt mechanism the non-goals explicitly want to avoid duplicating.
- **Critic visibility**: `evaluate_promotion` does **not** take critic
  findings directly. The critic BLOCKER/MAJOR loop stays a separate
  precondition to promotion, consistent with the craft-polish precedent
  cited in the source doc. Folding it in would turn a flat policy table
  into a rules engine — a stated non-goal.
- **`depends_on` short-circuiting**: `evaluate_promotion` always reports
  every gate's individual verdict in `reasons` (full picture, auditable).
  `depends_on` affects only whether a downstream gate's own failure can
  independently escalate `outcome` past what an upstream block already
  set — it never suppresses that gate's entry in `reasons`.

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-4,5,7    | Unit        | No `[policy]` block → identical outcome to today, clean and failing sets |
| FR-8        | Unit        | `required=false` failing gate does not block |
| FR-9        | Unit        | Unknown gate / bad `on_block` → `CONFIG_ERROR` |
| FR-6        | Unit        | `pause_for_human` rule → `outcome="pause_for_human"`, not `"block"` |
| FR-10       | Unit        | `depends_on` chain: all gate verdicts present in `reasons` regardless of outcome |
| FR-11       | Integration | `commands/gate.md` renders summary from `evaluate_promotion` output |
| FR-12       | Integration | Build repair loop halts via escalation path on `pause_for_human`, `status.md` unchanged |

## Tradeoffs

- **Chose reusing the escalation halt over a new pause state**: avoids a
  second "the flow stopped and is waiting on a human" mechanism, at the
  cost of the halt reading as "repair exhausted" even on a first-failure
  pause. Acceptable per the source doc's own correction.
- **Chose full-picture reporting over short-circuit reasons**: slightly more
  verbose `reasons` output, in exchange for a complete audit trail.

## Risks

- `_standards.md` `[policy]` parsing must fail closed on typos in gate
  names — mitigated by FR-9's `CONFIG_ERROR` requirement and unit coverage.
- Two call sites (`gate.md`, `build-ticket.md`) must be migrated together or
  they diverge again — mitigated by making both read the same
  `PromotionVerdict` in this ticket's implementation order.

## Implementation Order

1. `gates/policy.py`: dataclasses + `evaluate_promotion` (pure, unit-tested
   first per TDD).
2. `gates/policy.py`: `load_policy` parsing + `CONFIG_ERROR` handling.
3. `gates/config.py`: wire `[policy]` sub-block extraction.
4. `commands/gate.md`: replace inline check with `evaluate_promotion` call.
5. `context/flows/build-ticket.md`, `repair-escalation.md`: route
   `pause_for_human` through existing escalation halt.
6. `context/harness-reference.md`: document the policy table.
7. `tests/test_policy.py`: full outcome-matrix + parsing coverage.
