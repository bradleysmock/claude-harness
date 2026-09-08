# Design: Data-driven promotion policy

**Date:** 2026-09-03
**Status:** Proposed (not yet ticketed)
**Author:** Bradley + Claude
**Origin:** Comparison against agentic-dev-platform, where gate verdicts and the
promotion decision are separated: OPA evaluates policy over verdicts, so enabling
or disabling a gate changes a run without a policy-code edit.

## Problem

"Which gates block delivery, and what happens when one fails" is currently
expressed procedurally and in more than one place: `commands/gate.md`'s
fail-fast wiring, the critic BLOCKER/MAJOR auto-repair branch, and the
assumption — implicit in each suite runner — that every configured gate is
required and any failure makes the run non-zero. Changing that (making one gate
advisory, or adding a "pause for human" disposition) means touching several
call sites instead of one.

## Goal

One declarative policy table, `gate name → {required, on_block, depends_on}`,
and one pure function that evaluates a list of `GateResult` (and, optionally,
critic findings) against it to produce a single promotion verdict. Gate
*execution* and scheduling are untouched — only the pass/fail → promote/block
decision is centralized.

## Non-goals

- Replacing the scheduler (`gates/__init__.py`'s dependency-ordered
  `ThreadPoolExecutor`) — `depends_on` here is a promotion-policy concept
  (does gate B's *verdict* matter if gate A already blocked?), not an execution
  order.
- A general rules engine. The policy table is a flat, auditable list — not
  arbitrary logic — matching the harness's existing preference for pure,
  inspectable functions over cleverness.

## Architecture

### 1. `gates/policy.py` (new)

```python
@dataclass(frozen=True)
class PolicyRule:
    gate: str
    required: bool
    on_block: Literal["fail", "pause_for_human", "warn"]
    depends_on: tuple[str, ...] = ()

@dataclass(frozen=True)
class PromotionVerdict:
    outcome: Literal["promote", "block", "pause_for_human"]
    blocking_gates: tuple[str, ...]
    reasons: tuple[str, ...]

def load_policy(standards_text: str) -> list[PolicyRule]: ...
def evaluate_promotion(
    results: list[GateResult], policy: list[PolicyRule]
) -> PromotionVerdict: ...
```

`evaluate_promotion` is pure — no I/O, no subprocess — in the same spirit as
`repair_integrity.py`'s diff classifier: dataclasses in, a dataclass out, fully
unit-testable without a filesystem.

**Default policy** (no `[policy]` block present): every gate `required`,
`on_block = "fail"` — this reproduces today's exact behavior, so the feature is
additive for every project that doesn't opt in, the same guarantee
`ticket_templates.py` gives custom sections.

### 2. Config surface (`_standards.md`)

A `[policy]` sub-block inside the existing fenced `[gates]` region, parsed
fail-closed like every other override in `gates/config.py`:

```
```gates
[policy]
security.required = true
security.on_block = "pause_for_human"
lint.required = false
```
```

### 3. Wiring

`commands/gate.md`'s "a gate fails in any language makes the overall run
non-zero" line is replaced by one call to `evaluate_promotion`, and the printed
summary renders from its `outcome`/`reasons` instead of an inline boolean.
`context/flows/build-ticket.md`'s repair-loop decision (continue repairing vs.
stop) reads the same verdict.

### 4. `pause_for_human` disposition

**Correction (2026-09-03):** an earlier draft of this section treated
"pause for human" as a state the harness would need to invent. It doesn't —
`context/flows/repair-escalation.md` and `autopilot-ticket.md` already stop the
flow and hand the lead a decision when repair is exhausted, recording
`outcome="escalated"` via `memory(action="record", ...)` and pointing at the
`debug` skill. That existing shape is what a policy-triggered pause should
reuse, not a new ticket status.

Concretely: a gate whose rule sets `on_block = "pause_for_human"` and then
fails does **not** move the ticket to a new status. Instead, at the point
`evaluate_promotion` returns `outcome = "pause_for_human"`, the calling flow
(`build-ticket.md` or `repair-escalation.md`) stops the same way an exhausted
repair loop already stops: record `outcome="escalated"` in `.harness/memory.db`
for that gate, print the same "options" framing `autopilot-ticket.md` Step B
already uses, and leave the ticket's on-disk status untouched (`review-ready`
or `implementing`, whichever it already was) — the pause is a flow-level halt,
not a status transition. The lead resumes by re-running `/build` after acting,
same as today's exhausted-repair path. Unblocking it should record who made
the call via [[2026-09-03-identity-stamped-audit-log-design]].

## Files to change

- `gates/policy.py` — new.
- `gates/config.py` — parse the `[policy]` sub-block (or a sibling parser
  reusing its fenced-block machinery).
- `commands/gate.md` — call `evaluate_promotion` instead of the inline
  pass/fail check.
- `context/flows/build-ticket.md`, `context/flows/repair-escalation.md` —
  thread the verdict into the repair-loop decision, routing a
  `pause_for_human` outcome through the existing escalation halt rather than a
  new status.
- `context/harness-reference.md` — document the policy table and its reuse of
  the existing escalation shape.
- `tests/test_policy.py` — new.

## Verification

1. **Default-policy regression**: no `[policy]` block → identical outcome to
   today's all-required/any-failure-blocks behavior, for both a clean and a
   failing gate set.
2. **Non-required gate**: a failing gate marked `required = false` does not
   block promotion.
3. **Malformed policy**: an unknown gate name or invalid `on_block` value →
   `CONFIG_ERROR`, fails closed.
4. **Pause disposition**: a gate marked `pause_for_human` produces
   `outcome = "pause_for_human"` rather than `"block"`, and the build flow halts
   through the existing escalation path (recording `outcome="escalated"`,
   pointing at the `debug` skill) instead of failing the run outright.

## Open decisions for Checkpoint 1

1. Should a policy-triggered pause always route through the *exhausted-repair*
   escalation shape (as above), or does a gate that's meant to pause on its
   *first* failure — before any repair attempt — need a lighter-weight variant
   that doesn't imply retries were already tried?
2. Does `evaluate_promotion` need visibility into critic BLOCKER/MAJOR findings
   directly, or does the critic loop stay a separate precondition — the same
   way the craft-polish design treats critic approval as a precondition rather
   than folding it into one combined verdict?
3. Should `depends_on` short-circuit — skip evaluating a gate's disposition
   entirely if a prerequisite already blocked — or always report every gate's
   individual verdict for a complete picture even when the outcome is already
   decided?
