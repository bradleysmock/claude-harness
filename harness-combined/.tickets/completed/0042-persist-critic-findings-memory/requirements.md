# Requirements

**Ticket**: 0042
**Title**: Persist critic findings and escalation diagnoses; record failures to memory

## Functional Requirements

1. build-ticket.md Step 7 and each repair round must append the critic's structured
   report, headed by round number and date, to the ticket's critic-findings.md
   (alongside gate-findings.md) and commit it on the branch with that round.
2. repair-escalation.md must append the Phase 1 diagnostic output (root cause, fix
   strategy, target locations) to critic-findings.md and record it via
   memory(action="record") with gate "critic" before applying edits.
3. build-ticket.md Step 4e must call memory(action="record") with outcome "escalated"
   when a spec's gate loop exhausts MAX_REPAIR_ATTEMPTS, in addition to the existing
   passed-outcome record.
4. deliver-ticket.md Step 5 must scan critic-findings.md in addition to
   gate-findings.md when suggesting candidate learnings.
5. skills/review/SKILL.md and skills/debug/SKILL.md must read critic-findings.md when
   present and cite prior rounds instead of re-deriving them.

## Non-Functional Requirements

1. critic-findings.md is append-only during a ticket's life; the delivery squash
   archives it with the ticket.
2. No new tools or schema changes; memory.py's existing record shape is reused.

## Test Strategy

| Type | Rationale                                                          |
|------|---------------------------------------------------------------------|
| Unit | Docs greps for the five flow/skill wiring points                    |
| Unit | memory.record accepts gate "critic" and outcome "escalated" entries and retrieval surfaces them |

## Acceptance Criteria

- After a simulated two-round repair, critic-findings.md contains two dated round
  sections and one escalation section.
- memory.db contains an escalated record for an exhausted fixture loop and a critic
  record for the diagnosis; retrieve returns them for similar error text.
- deliver Step 5 output cites a pattern found only in critic-findings.md.

## Open Questions

- None.
