# Problem Statement

**Ticket**: 0042
**Title**: Persist critic findings and escalation diagnoses; record failures to memory
**Date**: 2026-07-05

## Problem

Post-build critic reports are only displayed, never persisted. The repair-escalation
diagnostic subagent produces the highest-value failure artifact in the pipeline (root
cause, failed strategies, fix strategy) and it is discarded when the run ends. The BM25
failure memory records only successes — build-ticket Step 4e records outcome "passed"
after a pass and nothing on exhaustion — so retrieval can never warn a future repair
away from an approach that already failed.

## Impact

- After escalation plus a context clear, the lead resumes /build with no durable record
  of findings or attempted repairs; /review re-derives everything.
- /deliver Step 5's candidate-learnings scan reads only gate-findings.md, so recurring
  critic-level patterns never reach _learnings.md (blocks ticket 0005's goal).
- memory(action="retrieve") returns success narratives only; failed strategies recur.

## Success Criteria

- Every critic round's report is appended to a per-ticket critic-findings.md, committed
  on the branch.
- Escalation diagnoses are persisted to the same file and recorded to memory.
- Exhausted repair loops record outcome "escalated" to memory.
- /deliver, /review, and /debug consume the persisted findings.

## Out of Scope

- Automated writes to _learnings.md (lead-curated; ticket 0005 owns suggestion flow).
- Changing critic report content or severity vocabulary.
