# Solution

**Ticket**: 0042
**Title**: Persist critic findings and escalation diagnoses; record failures to memory

## Approach

Introduce critic-findings.md as the per-ticket sibling of gate-findings.md, written by
the flows that already display critic output (no new machinery), and extend the two
memory-recording points so failures and diagnoses enter BM25 retrieval. All changes are
flow-doc edits plus memory-usage conventions; memory.py already supports the shapes.

## Components

| Component | Responsibility |
|-----------|----------------|
| critic-findings.md convention | Append-only per-round sections; documented in harness-reference.md |
| build-ticket.md edits | Step 7/7a append+commit; Step 4e escalated-outcome record |
| repair-escalation.md edits | Persist diagnosis; memory record with gate "critic" |
| deliver-ticket.md Step 5 edit | Scan both findings files for candidate learnings |
| review/debug skill edits | Read critic-findings.md when present |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Markdown sibling file over artifact JSON | Human-readable, squash-archived with the ticket, mirrors gate-findings.md |
| Reuse memory gate field ("critic") | Avoids schema change; BM25 already partitions by gate |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Docs grep: Step 7/7a contain append+commit instructions; reference section exists |
| FR-2 | Unit | Docs grep: escalation flow persists diagnosis and records memory |
| FR-3 | Unit | memory round-trip: escalated record written and retrievable |
| FR-4 | Unit | Docs grep: deliver Step 5 names critic-findings.md |
| FR-5 | Unit | Docs grep: review and debug skills read critic-findings.md |

## Tradeoffs

- **Chose flow-doc enforcement over a hook because**: the writer is the orchestrating
  model; a Stop-hook check for an un-updated critic-findings.md after critic rounds is a
  possible follow-up, not required for value.
- **Accepting risk of**: verbose files on long repair loops; round sections are capped
  by the existing size-discipline rule in the critique skill.

## Risks

- Duplicate content between displayed report and file — acceptable; the file is the
  durable copy.

## Implementation Order

1. Document the critic-findings.md convention in harness-reference.md.
2. Edit build-ticket.md (Step 7, 7a, 4e) and repair-escalation.md.
3. Edit deliver-ticket.md Step 5, review and debug skills.
4. Add memory round-trip tests and docs-grep tests.
