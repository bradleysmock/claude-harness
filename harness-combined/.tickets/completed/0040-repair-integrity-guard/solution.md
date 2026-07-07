# Solution

**Ticket**: 0040
**Title**: Repair-integrity guard against gate gaming

## Approach

Implement a pure diff classifier in gates/repair_integrity.py (mirroring the
spec_remediate.py pattern: pure functions, exhaustive unit tests), wire it into the two
repair-loop steps as a documented flow instruction, harden pre_write_guard's marker
handling, and add a suppression-delta section to stop_full_gate's report.

## Components

| Component | Responsibility |
|-----------|----------------|
| gates/repair_integrity.py | classify_diff(diff_text, language_hints) returning typed violations |
| build-ticket.md 4e/7a edits | Run check per round; violation fails the round with corrective brief |
| hooks/pre_write_guard.py | Reason-suffix requirement for justification markers |
| hooks/stop_full_gate.py | Net-new suppression count vs main in the blocking report |
| context/critic-brief.md | Step 2.5 weakened-tests BLOCKER instruction |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Regex-over-diff, not AST | Language-agnostic, fast, adequate for pragma/test-signature shapes |
| Pure module + flow wiring | Same architecture as spec_remediate.py; deterministic and testable |
| Reason suffix convention | Cheapest audit trail; avoids judging adequacy mechanically |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Violation fixtures per language and class; clean-diff negatives |
| FR-2 | Unit | Docs grep: 4e and 7a contain the integrity-check instruction |
| FR-3 | Unit | Bare marker blocked; reasoned marker passes; multi-marker lines |
| FR-4 | Unit | stop_full_gate reports two net-new bare pragmas on a fixture worktree diff |
| FR-5 | Unit | critic-brief Step 2.5 contains the weakened-test BLOCKER sentence |

## Tradeoffs

- **Chose regex classification over semantic analysis because**: the goal is catching
  mechanical gaming shapes, not proving equivalence; AST work per language is not worth
  the complexity at this layer.
- **Accepting risk of**: novel suppression syntaxes slipping through; the marker list is
  a named constant, easy to extend.

## Risks

- Legitimate test refactors (rename + move) can look like deletion — classifier counts
  net test-function delta per file pair, and the repair brief tells the model how to
  annotate a genuine move.

## Implementation Order

1. gates/repair_integrity.py with unit tests.
2. pre_write_guard reason-suffix change + tests.
3. stop_full_gate suppression-delta section + tests.
4. Flow edits: build-ticket 4e/7a, critic-brief Step 2.5, docs-grep tests.
