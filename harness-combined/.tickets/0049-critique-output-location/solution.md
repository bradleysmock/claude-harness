# Solution

**Ticket**: 0049
**Title**: Move /critique output out of cwd into .harness/critiques/

## Approach

Edit the critique skill's Output Format preamble to target
.harness/critiques/ with a slug-date-counter filename, add the ticket-pointer rule,
and extend the status skill's inventory to include the directory. Confirm ignore
coverage matches other .harness state.

## Components

| Component | Responsibility |
|-----------|----------------|
| skills/critique/SKILL.md | Output path, naming, ticket-pointer rule |
| skills/status/SKILL.md | Recent-critiques listing |
| init/docs ignore coverage | .harness/critiques/ ignored like results/ |
| tests/test_0049_critique_output_docs.py | Grep guards |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| .harness/critiques/ directory | Sits beside results/ and memory.db; already the harness state home |
| Slug-date-counter naming | Chronological sort, collision-free, human-scannable |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Grep: skill names the directory and naming scheme; no cwd CRITIQUE.md text |
| FR-2 | Unit | Ignore-coverage assertion; grep: never-inside-worktree rule present |
| FR-3 | Unit | Grep: ticket-pointer rule with the four fields |
| FR-4 | Unit | Grep: status skill lists recent critiques |

## Tradeoffs

- **Chose pointer-into-critic-findings over copying the report because**: one durable
  copy plus a pointer avoids divergence; critic-findings.md stays the per-ticket index
  (ticket 0042).

## Risks

- Sessions running /critique before any .harness exists — the skill creates the
  directory first.

## Implementation Order

1. Edit critique skill output section.
2. Ignore coverage + never-in-worktree rule.
3. Status skill listing.
4. Docs tests.
