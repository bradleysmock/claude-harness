# Requirements

**Ticket**: 0048
**Title**: Panel roster gaps and stale activation headers

## Functional Requirements

1. A GraphQL panel must exist (schema design, resolver N+1/dataloader, per-field
   authorization, query depth/complexity limits, persisted queries) with a trigger-table
   row activating on .graphql files and graphql/apollo/relay dependencies.
2. A gRPC/protobuf panel must exist (field-number immutability, wire compatibility,
   deadline propagation, retry/idempotency semantics, streaming patterns) with a row
   activating on .proto files and grpc dependencies.
3. A .NET panel must exist (async/await and ConfigureAwait discipline, IDisposable and
   DI lifetimes, EF Core query hygiene, nullable reference types) with a row activating
   on .cs/.csproj/.sln files.
4. Every file in context/panels/ must have its activation sentence replaced by a
   deferral line naming the trigger table in skills/critique/SKILL.md as the single
   activation source.
5. A consistency test must assert that every panel file referenced by the trigger
   table exists, every panel file is referenced by the table, and no panel file
   contains independent activation wording.

## Non-Functional Requirements

1. New panels follow the house format: named experts with positions tables, then
   numbered review dimensions with hazard tables; 40 to 90 lines each.
2. Expert selections must be genuinely tech-aware and current, not generic personas.

## Test Strategy

| Type | Rationale                                                        |
|------|--------------------------------------------------------------------|
| Unit | Table/panel bijection test; header-deferral grep across all panels |
| Unit | New rows parse in the table format the skills rely on              |

## Acceptance Criteria

- The trigger table contains rows for GraphQL, gRPC/protobuf, and .NET pointing at
  existing panel files in the house format.
- Grepping context/panels/ finds no "Active when" sentence that specifies file
  patterns; each header defers to the table.
- The bijection test passes for all panels including the three new ones.

## Open Questions

- None.
