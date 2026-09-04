# Solution

**Ticket**: 0074
**Title**: Data-driven promotion policy

## Approach

Add `gates/policy.py`: frozen dataclasses `PolicyRule`/`PromotionVerdict`
and two pure functions, `load_policy` and `evaluate_promotion`.
`commands/gate.md` and the build flows call `evaluate_promotion` instead of
each re-deriving pass/fail logic inline. Gate keys reuse the existing
`<language>.<gate>` dotted namespace from `gates/config.py` — no second gate
registry. Gate *execution* and scheduling are untouched.

## Components

| Component | Responsibility | Key interface |
|---|---|---|
| `gates/policy.py` | Policy model + pure evaluator | `load_policy(text)`, `evaluate_promotion(results, policy)` |
| `gates/config.py` | Parse `[policy]` sub-block; reuse `_VALID_LANGUAGES`/`_VALID_GATES` for validation | existing fenced-block parser |
| `commands/gate.md` | Render `outcome`/`reasons` instead of inline boolean | calls `evaluate_promotion` |
| `context/flows/build-ticket.md`, `autopilot-ticket.md` | On `pause_for_human`, run the policy-pause halt directly (no `repair-escalation.md` detour) | reads `PromotionVerdict.outcome` |
| `context/harness-reference.md` | Documents policy table + the policy-pause halt pattern | — |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Pure function, dataclasses in/out | Matches `repair_integrity.py`'s diff classifier — unit-testable without filesystem/subprocess |
| `<language>.<gate>` dotted keys, not bare names | `GateResult.gate` names collide across suites (e.g. `lint` in both Python and TypeScript); mirrors `gates/config.py`'s existing override-key format instead of inventing a second, ambiguous namespace |
| `[policy]` nested in existing `[gates]` fence | Reuses `gates/config.py`'s fail-closed fenced-block parser |
| Policy-pause halt as new lightweight step, not a `repair-escalation.md` call | That flow's Phase 1 hard-requires a critic report and repair-attempt history to diagnose; a gate paused on its first failure has neither |
| Default policy = today's behavior | Additive-by-default, same guarantee as `ticket_templates.py` |

## Decisions (resolves source doc's Checkpoint-1 questions)

- **Pause routing**: does **not** reuse `repair-escalation.md`'s diagnostic
  subagent — the critic found that flow's Phase 1 brief is hard-wired to
  consume "BLOCKER/MAJOR findings from the latest critic report" and
  "MAX_REPAIR_ATTEMPTS exhausted" context that don't exist for a
  first-failure policy pause. Instead, `build-ticket.md` and
  `autopilot-ticket.md` each gain a small, identical "policy pause halt"
  step: record `outcome="escalated"` (attempt=0, distinguishing it from a
  real repair-exhaustion record), print the same lead-options framing, skip
  the diagnostic subagent, leave `status.md` untouched. No new file, no new
  ticket status — reuses only the recording/messaging convention.
- **Critic visibility**: `evaluate_promotion` does not take critic findings
  directly; the critic loop stays a separate precondition, consistent with
  the craft-polish precedent. Avoids turning a flat table into a rules
  engine (non-goal).
- **`depends_on` semantics**: `reasons` always lists every gate's verdict
  (full audit trail, never suppressed). `depends_on` affects only
  `blocking_gates` — a failed gate is omitted from `blocking_gates` when a
  gate it `depends_on` also failed (presumed downstream symptom, not an
  independent root cause). `outcome` severity is computed from all
  required-gate dispositions regardless, so suppression never hides a real
  block/pause — it only trims the "fix these" list to root causes.
- **`on_block="warn"`**: included (source doc's type had three values,
  requirements.md originally dropped it — corrected). A failing required
  gate with `on_block="warn"` never contributes severity but always appears
  in `reasons`, distinct from `required=false` which is silent either way.

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-5,7,9    | Unit        | No `[policy]` block → identical outcome; `warn` never blocks but appears in `reasons` |
| FR-8        | Unit        | `required=false` failing gate never blocks |
| FR-4,6      | Unit        | Undotted key, unknown language/gate, bad `on_block` → `CONFIG_ERROR` |
| FR-11       | Unit        | Downstream failure suppressed from `blocking_gates`, present in `reasons` |
| —           | Unit        | `python.lint` and `typescript.lint` rules evaluated independently |
| FR-12       | Integration | `commands/gate.md` renders summary from `evaluate_promotion` output |
| FR-13       | Integration | Pause halt records memory, skips diagnostic subagent, `status.md` unchanged |

## Tradeoffs

- **Policy-pause halt duplicated in two flows over one shared flow file**:
  avoids inventing a third entry point into `repair-escalation.md`'s
  autopilot-only machinery; the halt logic is a few lines, documented once
  in `harness-reference.md` and referenced by both.
- **`blocking_gates` suppression over always-full `blocking_gates`**: costs
  a little computation to trace `depends_on` chains, buys a shorter,
  actionable "fix these" list without losing the audit trail in `reasons`.

## Risks

- `_standards.md` `[policy]` parsing must fail closed on typos — mitigated
  by reusing `gates/config.py`'s existing validation tables directly rather
  than duplicating them.
- `commands/gate.md` and both build flows must migrate together or drift
  recurs — mitigated by making all three read one `PromotionVerdict`.

## Implementation Order

1. Failing unit tests for `evaluate_promotion`'s outcome matrix (FR-7,9,11).
2. Implement `gates/policy.py` dataclasses + `evaluate_promotion` to pass.
3. Failing unit tests for `load_policy` (dotted keys, defaults, `CONFIG_ERROR`).
4. Implement `load_policy`; wire `gates/config.py`'s `[policy]` extraction.
5. Failing integration test + implement `commands/gate.md`'s
   `evaluate_promotion` call.
6. Failing integration test + implement the policy-pause halt in
   `build-ticket.md` and `autopilot-ticket.md`.
7. Document the policy table and pause-halt pattern in
   `context/harness-reference.md`.
