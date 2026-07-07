# Solution

**Ticket**: 0048
**Title**: Panel roster gaps and stale activation headers

## Approach

Author three thin panels in the established format (named experts, positions tables,
hazard-table dimensions), add their trigger rows and activation examples to the
critique skill's table, then sweep all panel headers to a one-line deferral and pin the
whole arrangement with a bijection test.

## Components

| Component | Responsibility |
|-----------|----------------|
| context/panels/graphql.md | Schema, resolver, authz, and cost-limiting hazards |
| context/panels/grpc-protobuf.md | Wire-compat, deadline, retry, streaming hazards |
| context/panels/dotnet.md | Async, DI-lifetime, EF Core, nullability hazards |
| skills/critique/SKILL.md | Three trigger rows + composite-activation examples |
| Panel header sweep | Deferral line across all existing panels |
| tests/test_0048_panel_consistency.py | Bijection + header-discipline guards |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Thin panels first | Removes the Core-only fallback now; depth can grow by follow-up |
| Deferral headers over deleting headers | Keeps each file self-explaining without duplicating triggers |
| Bijection test | Converts C2-style drift from a review finding into a failing test |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | graphql.md exists in house format; table row present and well-formed |
| FR-2 | Unit | grpc-protobuf.md exists; row present |
| FR-3 | Unit | dotnet.md exists; row present |
| FR-4 | Unit | Header grep: every panel defers; no file-pattern activation text remains |
| FR-5 | Unit | Bijection test across table and panels directory |

## Tradeoffs

- **Chose three panels over the full gap list because**: these are the stacks the
  trigger table can already meet with zero coverage; mobile/accessibility need deeper
  content work and their own tickets.
- **Accepting risk of**: thin panels missing hazards — the format makes extension
  cheap and the dimension numbering leaves room.

## Risks

- Dimension-number collisions with existing panels; allocate the next free numbers and
  note them in the table row.

## Implementation Order

1. Write the three panel files.
2. Add trigger rows and examples to the critique skill table.
3. Header sweep across existing panels.
4. Bijection/header tests; full suite.
