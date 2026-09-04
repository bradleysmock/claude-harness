# Requirements

**Ticket**: 0074
**Title**: Data-driven promotion policy

## Functional Requirements

1. The system must provide `PolicyRule` and `PromotionVerdict` frozen
   dataclasses in `gates/policy.py`.
2. The system must provide `load_policy(standards_text) -> list[PolicyRule]`,
   parsing a `[policy]` sub-block inside the existing fenced `[gates]`
   region.
3. The system must provide `evaluate_promotion(results, policy) ->
   PromotionVerdict` as a pure function: no I/O, no subprocess.
4. A policy rule's gate key must use the same `<language>.<gate>` dotted
   form as the existing `[gates]` override syntax (`gates/config.py`); a
   bare, undotted key is a `CONFIG_ERROR` — one gate namespace, not two.
5. With no `[policy]` block, `load_policy` must default every known
   `<language>.<gate>` pair to `required=True, on_block="fail"` (today's
   behavior).
6. `on_block` accepts exactly `{"fail", "pause_for_human", "warn"}`; any
   other value, unknown language, or unknown gate (validated against
   `gates/config.py`'s existing `_VALID_LANGUAGES`/`_VALID_GATES`) is a
   `CONFIG_ERROR`.
7. A failed required gate with `on_block="fail"` contributes `block`
   severity; `"pause_for_human"` contributes `pause_for_human` severity;
   `"warn"` contributes no severity but is still recorded in `reasons`.
8. A gate marked `required=False` never contributes severity, regardless of
   `on_block` or result.
9. `outcome` is the worst severity across all required-gate dispositions
   (`block` > `pause_for_human` > `promote`).
10. `reasons` must include one entry per evaluated gate, always (full
    picture, never suppressed): `"<gate>: <on_block> (<passed|failed>)"`.
11. `blocking_gates` includes a failed required gate only if none of its
    `depends_on` gates also failed — a failure whose `depends_on` prereq
    already failed is presumed a downstream consequence and is omitted from
    `blocking_gates` (but never from `reasons`).
12. `commands/gate.md` must replace its inline pass/fail check with one call
    to `evaluate_promotion`, rendering its summary from `outcome`/`reasons`.
13. On `outcome="pause_for_human"`, the calling flow (`build-ticket.md`'s
    interactive halt, or `autopilot-ticket.md` Step B) performs a "policy
    pause halt": records `memory(..., outcome="escalated", attempt=0)` for
    the pausing gate, prints the same lead-facing options framing already
    used for exhausted repair, and leaves `status.md` untouched. It must
    NOT invoke `repair-escalation.md`'s Phase 1 diagnostic subagent — no
    critic findings or repair history exist to diagnose on a first pause.

## Non-Functional Requirements

1. Backward compatibility: no `[policy]` block yields byte-identical
   promotion behavior to today, clean and failing gate sets alike.
2. Auditability: policy is a flat, inspectable table; no expressions.
3. No second gate-name registry: policy validation reuses
   `gates/config.py`'s `_VALID_LANGUAGES`/`_VALID_GATES`.

## Test Strategy

| Type        | Rationale                                              |
|-------------|-----------------------------------------------------------|
| Unit        | `evaluate_promotion` outcome matrix incl. `warn` (FR-7,9) |
| Unit        | `blocking_gates` suppression via `depends_on` (FR-11)      |
| Unit        | `load_policy` defaults, dotted-key + `CONFIG_ERROR` (FR-4-6) |
| Unit        | Polyglot: `python.lint` and `typescript.lint` rules independent |
| Integration | `commands/gate.md` renders from `evaluate_promotion`       |
| Integration | Pause halt records memory + skips diagnostic subagent (FR-13) |

## Acceptance Criteria

- No `[policy]` block: outcome matches today's behavior.
- `required=false` failing gate never blocks; `on_block="warn"` failing
  required gate never blocks but appears in `reasons`.
- Undotted key, unknown language/gate, or bad `on_block` -> `CONFIG_ERROR`.
- A `pause_for_human` gate halts via the lightweight pause halt (no
  diagnostic subagent invoked), `status.md` unchanged.
- A gate suppressed from `blocking_gates` by `depends_on` still appears in
  `reasons`.

## Open Questions

None — the checkpoint questions from the source design doc are resolved in
`solution.md § Decisions`, for lead confirmation at Checkpoint 1.
