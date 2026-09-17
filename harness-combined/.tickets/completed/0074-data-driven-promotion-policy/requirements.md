# Requirements

**Ticket**: 0074
**Title**: Data-driven promotion policy

## Functional Requirements

1. The system must provide `PolicyRule` and `PromotionVerdict` frozen
   dataclasses in `gates/policy.py`.
2. The system must provide `load_policy(standards_text) -> list[PolicyRule]`,
   parsing a `[policy]` sub-block inside the existing fenced `[gates]`
   region.
3. The system must provide `evaluate_promotion(language_results:
   list[LanguageResult], global_results: list[GateResult], policy:
   list[PolicyRule]) -> PromotionVerdict` as a pure function: no I/O, no
   subprocess. `global_results` covers gates that run once, independent of
   any language dispatch (currently only `commit_lint`).
4. A policy rule's gate key is either `<language>.<gate>` (validated against
   a new `_POLICY_LANGUAGE_GATES` table in `gates/policy.py` — a superset of
   `gates/config.py`'s `_VALID_GATES` that also covers the cross-cutting
   gates every `run_suite_on_dir` call appends per language: `secrets`,
   `coverage`, `dep-audit`, `sast`) or `global.<gate>` (validated against
   `_POLICY_GLOBAL_GATES = {"commit_lint"}`). Any other form is
   `CONFIG_ERROR` — one explicit namespace per gate, never a bare name.
5. With no `[policy]` block, `load_policy` must default every gate in
   `_POLICY_LANGUAGE_GATES`/`_POLICY_GLOBAL_GATES` to `required=True,
   on_block="fail"` (today's behavior).
6. `on_block` accepts exactly `{"fail", "pause_for_human", "warn"}`; any
   other value or a key outside FR-4's namespaces is a `CONFIG_ERROR`.
7. A failed required gate with `on_block="fail"` contributes `block`
   severity; `"pause_for_human"` contributes `pause_for_human` severity;
   `"warn"` contributes no severity but is still recorded in `reasons`.
8. A gate marked `required=False` never contributes severity, regardless of
   `on_block` or result.
9. `outcome` is the worst severity across all required-gate dispositions
   (`block` > `pause_for_human` > `promote`).
10. `reasons` must include one entry per evaluated gate, always (full
    picture, never suppressed): `"<gate>: <on_block>
    (<passed|failed|skipped>)"`.
11. `blocking_gates` includes a failed required gate only if none of its
    `depends_on` gates also failed. `load_policy` must validate every
    `depends_on` entry against the same namespaces as FR-4 — an unresolvable
    reference is `CONFIG_ERROR`, not a silent no-op.
12. `commands/gate.md` must replace its inline pass/fail check with one call
    to `evaluate_promotion`, rendering its summary from `outcome`/`reasons`.
13. `context/flows/build-ticket.md` Step 4f (per-repair-attempt gate check)
    and Step 7a (final re-run check) must read `evaluate_promotion`'s
    `outcome` instead of the raw gate-result boolean, so a `pause_for_human`
    or `warn` rule takes effect during `/build`, not only `/gate`.
14. On `outcome="pause_for_human"`, the calling flow performs a "policy
    pause halt": records `memory(..., outcome="escalated", attempt=0)` for
    the pausing gate, prints the same lead-facing options framing
    `autopilot-ticket.md` **Step A** ("Repair exhaustion") already uses, and
    leaves `status.md` untouched — reusing Step A's halt point, never
    Step B ("Auto-deliver"), which has no lead checkpoint at all. It must
    NOT invoke `repair-escalation.md`'s Phase 1 diagnostic subagent.

## Non-Functional Requirements

1. Backward compatibility: no `[policy]` block yields byte-identical
   promotion behavior to today, for every gate including cross-cutting ones.
2. Auditability: policy is a flat, inspectable table; no expressions.
3. Policy validation tables live in `gates/policy.py`, distinct from
   `gates/config.py`'s override-command tables (different purpose, wider
   gate surface) — no gate name is invisible to policy.

## Test Strategy

| Type        | Rationale                                              |
|-------------|-----------------------------------------------------------|
| Unit        | `evaluate_promotion` outcome matrix incl. `warn` (FR-7,9) |
| Unit        | `blocking_gates` suppression via `depends_on` (FR-11)      |
| Unit        | `load_policy`: dotted + `global.` keys, `CONFIG_ERROR`s (FR-4-6,11) |
| Unit        | Cross-cutting gate (`python.secrets`, `global.commit_lint`) policy rules |
| Integration | `commands/gate.md` renders from `evaluate_promotion`       |
| Integration | `/build` Step 4f/7a halt on `pause_for_human` (FR-13,14)   |

## Acceptance Criteria

- No `[policy]` block: outcome matches today's behavior, all gates included.
- `required=false` never blocks; `on_block="warn"` never blocks but appears
  in `reasons`.
- Bad key form/language/gate, unresolvable `depends_on`, or bad `on_block`
  -> `CONFIG_ERROR`.
- A `pause_for_human` gate halts `/build` via Step A's framing (no
  diagnostic subagent), `status.md` unchanged — not just `/gate`.

## Open Questions

None — the checkpoint questions from the source design doc are resolved in
`solution.md § Decisions`, for lead confirmation at Checkpoint 1.
