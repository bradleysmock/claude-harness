# Solution

**Ticket**: 0005
**Title**: Automated Learnings Capture

## Approach

Extend `deliver-ticket.md` (Step 7) to parse `gate-findings.md` and emit formatted ready-to-paste candidate lines for lead review; the model never writes `_learnings.md` from raw extracted text — it constructs the append string from validated template fields only after the lead accepts. A new `/harvest-learnings` command applies the same flow but sources patterns from `memory.db` via per-gate-type queries. Critic-findings extraction is out of scope (no persistent artifact exists).

## Components

| Component | Responsibility | Key Interface |
|---|---|---|
| `context/helpers/parse-gate-findings.md` | Parses `gate-findings.md` → structured candidate list; sanitizes pattern field; caps at 5; prioritizes BLOCKER/MAJOR | Outputs `[{date, gate, ticket, pattern, severity}]` |
| `context/helpers/parse-memory-findings.md` | Queries `memory.db` per gate type; aggregates by recurrence (≥2); sanitizes pattern field | Outputs `[{date, gate, ticket:"multi", pattern, severity}]` |
| `context/helpers/candidate-learnings-flow.md` | Deduplicates by lowercased/whitespace-collapsed pattern vs existing `_learnings.md`; presents ready-to-paste lines; accept/reject loop; appends accepted entries constructed from template fields | Input: normalized candidate list + target file path |
| `context/flows/deliver-ticket.md` Step 7 (revised) | Calls parse-gate-findings.md then candidate-learnings-flow.md; skips silently if no candidates | Replaces existing suggestion block |
| `commands/harvest-learnings.md` | Calls parse-memory-findings.md then candidate-learnings-flow.md; accepts optional gate-name filter | Entry point |

## Tech Choices

| Choice | Rationale |
|---|---|
| Paste-block / template-field append (not raw-text write) | Eliminates Willison lethal trifecta: model never holds write tool + raw attacker-influenced text simultaneously |
| Sanitize in parse helpers (before display) | Reject candidate at source so candidate-learnings-flow never sees unsanitized content |
| Per-gate-type `memory(action="retrieve", ...)` queries | BM25 requires real terms; `"*"` is not a wildcard; representative terms per gate give meaningful retrieval |
| Recurrence threshold ≥2 for harvest-learnings | Filters one-off noise; explicitly specified so threshold is testable |
| Candidate line format: `<date> \| <gate> \| XXXX \| <pattern>` | Provenance tracking; enables pruning; backward-compatible |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|---|---|---|
| FR-1 | Integration | Fixture: 3 BLOCKER failures in gate-findings.md → 3 candidates in deliver report |
| FR-1 cap+priority | Integration | Fixture: 8 failures (2 BLOCKER, 6 MINOR) → 5 proposed; 2 BLOCKERs present |
| FR-2/3 accept | Integration | Lead accepts entry 1, rejects entry 2 → only entry 1 in `_learnings.md` |
| FR-3 template | Integration | Appended line matches template `{date} | {gate} | {ticket} | {pattern}` exactly |
| FR-4 sanitize | Integration | gate-findings.md message contains `## heading`, `<xml-tag>`, imperative directive → sanitized or not proposed |
| FR-5 recurrence | Integration | memory.db seeded with gate X appearing 1×, gate Y appearing 3× → only gate Y proposed |
| FR-6 | Integration | `/harvest-learnings` accept → `_learnings.md` entry has ticket field `multi` |
| FR-7 dedup | Integration | Pattern already in `_learnings.md` → not re-proposed |
| FR-8 | Integration | Empty `gate-findings.md` → no "Candidate learnings" section |
| FR-9 stub | Integration | `_learnings.md` absent → stub created; entry appended |
| FR-10 no-overwrite | Integration | Pre-existing content in `_learnings.md` intact after append |
| FR-5 empty db | Integration | Sparse memory.db (no pattern ≥2) → "No recurring patterns found" |
| FR-11 | — | xref requirements.md FR-11 |

## Tradeoffs

- **Chose paste-block / template-field append over in-session raw-text append**: Architectural solution to injection trifecta; trades minor lead convenience (no one-click accept) for elimination of a persistent write-path vulnerability.
- **Chose recurrence threshold of 2 over higher values**: Low threshold surfaces patterns early; lead review is the final guard against noise.
- **Accepting risk of**: Stale patterns in memory.db resurfacing via `/harvest-learnings`. Mitigation: lead review before accepting; no time-window filter in v1.

## Risks

- `gate-findings.md` format varies between gate types → tolerant parsing; only `gate` + `message` fields required; missing fields skip the candidate.
- Sanitization heuristics may miss novel injection patterns → architectural mitigation (template-field-only append) means even a missed sanitization does not produce a write from raw attacker text.
- `harness-reference.md` and `deliver-ticket.md` contain contradictory prose post-implementation unless FR-11 is completed → implementation order enforces this as step 7.

## Implementation Order

1. Write integration test fixtures: `gate-findings.md` stubs (varied severity, injection payloads); seed script for `memory.db`.
2. Write `context/helpers/parse-gate-findings.md` against test fixtures (sanitization + priority + cap).
3. Write `context/helpers/parse-memory-findings.md` (per-gate queries, recurrence threshold ≥2, sanitization).
4. Write `context/helpers/candidate-learnings-flow.md` (dedup, accept/reject loop, template-field append).
5. Revise `context/flows/deliver-ticket.md` Step 7 to call parse-gate-findings.md → candidate-learnings-flow.md.
6. Write `commands/harvest-learnings.md`.
7. Update `context/harness-reference.md` Memory Contract table and `deliver-ticket.md` Step 7 prose (FR-11).
8. Run all integration test scenarios; verify `_learnings.md` output and sanitization correctness.
