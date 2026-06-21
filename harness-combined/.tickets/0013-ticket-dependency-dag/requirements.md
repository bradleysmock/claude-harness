# Requirements

**Ticket**: 0013
**Title**: Ticket dependency field and DAG visualization

## Functional Requirements

1. The system must support a `depends-on:` field in `status.md` whose value is a comma-separated list of four-digit ticket numbers (e.g. `depends-on: 0010, 0011`).
2. The system must treat absence of `depends-on:` identically to an empty list (no dependencies).
3. `/build XXXX` must read `depends-on:` from the target ticket's `status.md`, resolve each listed ticket's current status, and block with a structured error message (naming each unresolved dependency and its status) if any dependency is not in `done` status.
4. `/ticket-status` must read `depends-on:` from every open and completed ticket's `status.md` and build a dependency graph.
5. `/ticket-status` must render the dependency graph as a topologically-sorted text execution-order list (wave-based, matching existing Implementation Order section format).
6. `/ticket-status` must render the dependency graph as a Mermaid `graph TD` diagram embedded in its output.
7. Cycle detection must run whenever `status.md` is written with a `depends-on:` field — at design-write time in `/problem` and at any subsequent status transition — and must raise a clear, named-cycle error before completing the write.
8. Dependency lookup must search both `.tickets/` and `.tickets/completed/` to allow depending on already-completed tickets.
9. A dependency on a non-existent ticket number must raise a validation error at write time (not silently ignored).

## Non-Functional Requirements

1. Cycle detection must complete in O(N+E) time using depth-first search across all known tickets.
2. The Mermaid diagram must render correctly in GitHub Markdown and standard Mermaid-compatible viewers.
3. The dependency enforcement in `/build` must not perform filesystem-expensive scans more than once per invocation.

## Test Strategy

| Type        | Rationale                                              |
|-------------|--------------------------------------------------------|
| Unit        | DAG construction, cycle detection, topological sort, status.md parsing, Mermaid diagram generation |
| Integration | `/build` blocks on unresolved dep; `/build` proceeds when all deps done; `/ticket-status` renders graph correctly with mixed dep states |

## Acceptance Criteria

- A `status.md` with `depends-on: 0010, 0011` is parsed correctly; missing field parses as empty.
- Writing `depends-on:` that creates a cycle raises a named error; write is rejected.
- Writing `depends-on:` with a non-existent ticket raises a validation error; write is rejected.
- `/build 0013` with dependency on non-done ticket prints an error naming the blocking ticket and its status; build does not proceed.
- `/build 0013` with all dependencies in `done` status proceeds normally.
- `/ticket-status` output includes a Mermaid `graph TD` block and a text execution-order section reflecting declared dependencies.
- All unit and integration tests pass under the standard gate suite.

## Open Questions

- None.
