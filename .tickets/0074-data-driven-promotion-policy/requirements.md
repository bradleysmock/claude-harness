# Requirements

**Ticket**: 0074
**Title**: Data-driven promotion policy

## Functional Requirements

1. The system must provide `PolicyRule` and `PromotionVerdict` frozen
   dataclasses in `gates/policy.py` as specified in the design.
2. The system must provide `load_policy(standards_text) -> list[PolicyRule]`,
   parsing a `[policy]` sub-block inside the existing fenced `[gates]` region
   of `_standards.md`.
3. The system must provide `evaluate_promotion(results, policy) ->
   PromotionVerdict` as a pure function: no I/O, no subprocess calls.
4. When no `[policy]` block is present, `load_policy` must return a default
   policy where every known gate is `required=True`, `on_block="fail"`.
5. `evaluate_promotion` must return `outcome="block"` when any required gate
   with `on_block="fail"` has failed.
6. `evaluate_promotion` must return `outcome="pause_for_human"` when a failed
   gate's rule has `on_block="pause_for_human"`, and no unresolved `"fail"`
   disposition outranks it.
7. `evaluate_promotion` must return `outcome="promote"` when no required gate
   with `on_block` in `{"fail", "pause_for_human"}` has failed.
8. A gate marked `required=False` must not affect the outcome regardless of
   its result.
9. `load_policy` must reject an unknown gate name or an invalid `on_block`
   value with a fail-closed `CONFIG_ERROR`, never silently ignoring it.
10. `evaluate_promotion` must report every gate's individual verdict in
    `reasons`/`blocking_gates`, regardless of `depends_on` ordering — full
    picture, not first-blocker-only.
11. `commands/gate.md` must replace its inline pass/fail check with one call
    to `evaluate_promotion`, rendering the summary from `outcome`/`reasons`.
12. `context/flows/build-ticket.md` and `repair-escalation.md` must route a
    `pause_for_human` outcome through the existing exhausted-repair
    escalation halt (`memory(action="record", outcome="escalated")`,
    `debug` skill pointer), leaving ticket `status.md` untouched.

## Non-Functional Requirements

1. Backward compatibility: a project with no `[policy]` block must see
   byte-for-byte identical promotion behavior to today, for both clean and
   failing gate sets.
2. Auditability: policy is a flat, inspectable table — no arbitrary
   expressions or callables in `_standards.md`.

## Test Strategy

| Type        | Rationale                                              |
|-------------|---------------------------------------------------------|
| Unit        | `evaluate_promotion` outcome matrix (FR-5..10) in isolation from I/O |
| Unit        | `load_policy` parsing, defaults, and `CONFIG_ERROR` cases (FR-2,4,9) |
| Integration | `commands/gate.md` end-to-end with a policy block present/absent |
| Integration | Build repair loop halts correctly on `pause_for_human` (FR-12) |

## Acceptance Criteria

- No `[policy]` block: outcome matches today's behavior for both a clean and
  a failing gate set.
- A failing gate marked `required=false` does not block promotion.
- An unknown gate name or invalid `on_block` value raises `CONFIG_ERROR`.
- A `pause_for_human` gate produces that outcome and the build flow halts via
  the existing escalation path, not a hard failure or a new ticket status.

## Open Questions

None — the three checkpoint questions raised in the source design doc
(pause routing, critic-visibility, `depends_on` short-circuit) are resolved
as design decisions in `solution.md § Tradeoffs`, for lead confirmation at
Checkpoint 1.
