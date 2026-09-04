# Solution

**Ticket**: 0074
**Title**: Data-driven promotion policy

## Approach

Add `gates/policy.py`: frozen dataclasses `PolicyRule`/`PromotionVerdict`
and two pure functions, `load_policy` and `evaluate_promotion`.
`evaluate_promotion` takes the actual runtime shapes — `list[LanguageResult]`
for per-language dispatched gates and `list[GateResult]` for the few gates
that run once, independent of language (`commit_lint`) — and returns one
verdict. `commands/gate.md` and `build-ticket.md`'s repair loop both call it
instead of re-deriving pass/fail inline. Gate execution/scheduling untouched.

## Components

| Component | Responsibility | Key interface |
|---|---|---|
| `gates/policy.py` | Policy model, two validation tables, pure evaluator | `load_policy(text)`, `evaluate_promotion(language_results, global_results, policy)` |
| `gates/config.py` | Parse `[policy]` sub-block (text extraction only; validation lives in `gates/policy.py`) | existing fenced-block parser |
| `commands/gate.md` | Render `outcome`/`reasons` instead of inline boolean | calls `evaluate_promotion` |
| `context/flows/build-ticket.md` | Step 4f/7a read `outcome` instead of raw pass/fail; policy-pause halt on `pause_for_human` | reads `PromotionVerdict` |
| `context/flows/autopilot-ticket.md` | Policy-pause halt reuses Step A's framing, never Step B | reads `PromotionVerdict` |
| `context/harness-reference.md` | Documents policy table + policy-pause halt pattern | — |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Pure function, dataclasses in/out | Matches `repair_integrity.py`'s diff classifier — no filesystem/subprocess |
| Two key namespaces: `<language>.<gate>` and `global.<gate>` | `secrets`/`coverage`/`dep-audit`/`sast` are appended per-language inside each `LanguageResult` (real dotted addresses); `commit_lint` runs once, outside any `LanguageResult` — one namespace can't honestly cover both |
| New `_POLICY_LANGUAGE_GATES`/`_POLICY_GLOBAL_GATES` tables in `gates/policy.py`, not a reuse of `gates/config.py`'s `_VALID_GATES` | `_VALID_GATES` scopes *overridable commands*, a narrower purpose than *addressable-by-policy*; reusing it verbatim would silently make `secrets`/`commit_lint` unwritable in policy — corrected from an earlier, incorrect "just reuse it" plan |
| Policy-pause halt reuses Step A's message/record pattern only, not `repair-escalation.md`'s diagnostic subagent | That subagent hard-requires a critic report and repair-attempt history a first-failure pause doesn't have |
| Default policy = today's behavior | Additive-by-default, same guarantee as `ticket_templates.py` |

## Decisions (resolves source doc's Checkpoint-1 questions)

- **Pause routing**: reuses `autopilot-ticket.md` **Step A**'s halt framing
  (record `outcome="escalated"`, attempt=0, print lead options), applied
  identically from `build-ticket.md`'s interactive path. Explicitly **not**
  Step B ("Auto-deliver"), which has no lead checkpoint — routing there
  would let a `pause_for_human` verdict silently auto-deliver. Skips
  `repair-escalation.md`'s diagnostic subagent (no findings to diagnose).
- **Critic visibility**: `evaluate_promotion` does not take critic findings;
  the critic loop stays a separate precondition (craft-polish precedent).
- **`depends_on` semantics**: `reasons` always lists every gate's verdict.
  `depends_on` affects only `blocking_gates` (a gate is omitted there if a
  gate it depends on also failed — presumed symptom, not root cause).
  `outcome` severity is computed from all required-gate dispositions
  regardless, so suppression never hides a real block/pause.
- **`on_block="warn"`**: included as a third disposition — never blocks,
  always appears in `reasons`, distinct from `required=false`.
- **Cross-cutting gates**: addressed via `global.<gate>` for gates with no
  language dispatch, and via ordinary `<language>.<gate>` for gates that
  run per-language even though they aren't per-language *code* (`secrets`,
  `coverage`, `dep-audit`, `sast` each appear inside every `LanguageResult`
  today, so `python.secrets` and `typescript.secrets` are legitimately
  distinct, if redundant, addresses).

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-5,7,9    | Unit        | No `[policy]` block → identical outcome incl. cross-cutting gates |
| FR-8        | Unit        | `required=false` never blocks |
| FR-4,6,11   | Unit        | Bad key form, unresolvable `depends_on`, bad `on_block` → `CONFIG_ERROR` |
| FR-4        | Unit        | `global.commit_lint` and `python.secrets` both resolve correctly |
| FR-11       | Unit        | Downstream failure suppressed from `blocking_gates`, present in `reasons` |
| FR-12       | Integration | `commands/gate.md` renders from `evaluate_promotion` output |
| FR-13,14    | Integration | `/build` Step 4f/7a halts via Step A's framing on `pause_for_human` |

## Tradeoffs

- **Two key namespaces over one**: more surface area than a single dotted
  scheme, but honest about the runtime split between per-language and
  global gates rather than forcing global gates into a fake language slot.
- **`blocking_gates` suppression over always-full list**: a little
  `depends_on`-chain tracing, buys a shorter "fix these" list without
  losing the audit trail in `reasons`.

## Risks

- New validation tables (`_POLICY_LANGUAGE_GATES`/`_POLICY_GLOBAL_GATES`)
  duplicate knowledge of the gate surface alongside `gates/config.py`'s
  `_VALID_GATES` — mitigated by a same-file comment cross-referencing both,
  and a unit test asserting `_VALID_GATES[lang] <= _POLICY_LANGUAGE_GATES[lang]`.
- `commands/gate.md` and `build-ticket.md` must migrate together or drift
  recurs — mitigated by both reading one `PromotionVerdict`.

## Implementation Order

1. Failing unit tests for `evaluate_promotion`'s outcome matrix (FR-7,9,11).
2. Implement `gates/policy.py` dataclasses + `evaluate_promotion`.
3. Failing unit tests for `load_policy` (both namespaces, defaults,
   `CONFIG_ERROR`s).
4. Implement `load_policy` + the two validation tables; wire
   `gates/config.py`'s `[policy]` text extraction.
5. Failing integration test + implement `commands/gate.md`'s
   `evaluate_promotion` call.
6. Failing integration test + implement `build-ticket.md` Step 4f/7a reading
   `outcome`, and the policy-pause halt (reusing Step A's framing) in both
   `build-ticket.md` and `autopilot-ticket.md`.
7. Document the policy table and pause-halt pattern in
   `context/harness-reference.md`.
