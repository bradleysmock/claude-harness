# Problem Statement

**Ticket**: 0013
**Title**: Ticket dependency field and DAG visualization
**Date**: 2026-06-21

## Problem

The harness manages multiple tickets but has no mechanism to declare ordering or blocking relationships between them. When a multi-ticket feature build requires specific sequencing—where ticket B cannot begin until ticket A is done—there is no way to express or enforce this. Engineers must track dependencies manually or risk starting dependent work before prerequisites are complete.

## Impact

- Harness operators running multi-ticket feature builds may start `/build` on a dependent ticket before its dependencies are done, producing incomplete or broken output.
- There is no way to visualize the execution order of a set of related tickets, making planning and coordination harder.
- Without cycle detection, circular dependencies could be declared silently, making the dependency graph unresolvable.

## Success Criteria

- `status.md` accepts a `depends-on:` field listing one or more ticket numbers (e.g. `depends-on: 0010, 0011`).
- `/build XXXX` reads `depends-on:` and blocks with a clear error message if any listed dependency ticket's status is not `done`.
- `/ticket-status` renders the full dependency graph as: (1) a topologically-sorted text execution-order list, and (2) a Mermaid `graph TD` diagram.
- Cycle detection runs at write time (when `status.md` is written with a `depends-on:` field) and raises a clear error if a cycle is detected.
- All new behaviors are covered by unit and integration tests.

## Out of Scope

- Automatic dependency resolution or ticket auto-sequencing (the harness does not decide order for the user).
- Cross-repository ticket dependencies.
- Partial-done dependency states (a dependency is either done or not done — no percentage thresholds).
- UI beyond the Mermaid diagram and text list already described.
