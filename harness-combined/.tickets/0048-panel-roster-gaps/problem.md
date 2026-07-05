# Problem Statement

**Ticket**: 0048
**Title**: Panel roster gaps and stale activation headers
**Date**: 2026-07-05

## Problem

The critique trigger table can encounter stacks that have no panel at all — a C#/.NET
worktree activates Core only; GraphQL schemas and resolvers match nothing; .proto and
gRPC service definitions match nothing — so those reviews silently lose the
domain-expert lens the panel system exists to provide. Separately, several panel files
carry their own activation sentences that have drifted from the authoritative trigger
table (context/panels/python.md claims activation on app/ and tests/ paths while the
table activates on any .py file), and the critic subagent reads both sources.

## Impact

- .NET, GraphQL, and gRPC changes get generic Core review instead of domain hazards
  (async/await pitfalls and EF query patterns; resolver N+1 and per-field authz; wire
  compatibility and deadline propagation).
- Drifted activation headers can cause the critic to skip a panel the table would
  activate — a silent review-coverage loss.

## Success Criteria

- Thin but real panels exist for GraphQL, gRPC/protobuf, and .NET, wired into the
  trigger table.
- No panel file carries independent activation text; all defer to the table.
- A consistency test guards header discipline and table/panel-file agreement.

## Out of Scope

- Mobile (Swift/Android) and accessibility-specialist panels — candidate follow-ups,
  larger content efforts.
- Gate support for .NET (panels are review-layer only).
