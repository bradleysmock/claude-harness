# Spec Coverage Map

**Ticket**: 0065-tdd-order-build-step4
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| AC-1 | AC | The helper reports `red` against a test with no implementation, `blocking` | 0065-tdd-order-build-step4-red-gate |
| FR-1 | FR | Step 4 must write a spec's test file before any implementation is generated. | — |
| FR-2 | FR | The flow must run a deterministic red-gate check against only the newly | — |
| FR-3 | FR | The check must classify its result as `red` (genuine failure attributable to | — |
| FR-4 | FR | `blocking` must revise and rewrite the test up to `MAX_REPAIR_ATTEMPTS` | — |
| FR-5 | FR | `tool_error` must not consume a retry attempt; it escalates immediately on | — |
| FR-6 | FR | On budget exhaustion (FR-4) or a `tool_error` (FR-5), the flow must skip | — |
| FR-7 | FR | After `red` is confirmed, implementation must be generated and written | — |
| FR-8 | FR | Step 4e (`gate_run_on_dir`, full-suite, its repair loop and | — |
| FR-9 | FR | The classification in FR-3/FR-5 must be a deterministic Python component, | — |
| FR-10 | FR | The check must support Python, TypeScript, Go, and Rust, scoped to the new | — |
| AC-2 | AC | A new test sharing a file with an unrelated pre-existing failure is still | — |
| AC-3 | AC | `build-ticket.md` Step 4 instructs writing tests, gating red, writing | — |
| AC-4 | AC | Step 4e's gate, repair loop, and `MAX_REPAIR_ATTEMPTS` are unchanged. | — |

## Uncovered

- FR-1 (FR): Step 4 must write a spec's test file before any implementation is generated.
- FR-2 (FR): The flow must run a deterministic red-gate check against only the newly
- FR-3 (FR): The check must classify its result as `red` (genuine failure attributable to
- FR-4 (FR): `blocking` must revise and rewrite the test up to `MAX_REPAIR_ATTEMPTS`
- FR-5 (FR): `tool_error` must not consume a retry attempt; it escalates immediately on
- FR-6 (FR): On budget exhaustion (FR-4) or a `tool_error` (FR-5), the flow must skip
- FR-7 (FR): After `red` is confirmed, implementation must be generated and written
- FR-8 (FR): Step 4e (`gate_run_on_dir`, full-suite, its repair loop and
- FR-9 (FR): The classification in FR-3/FR-5 must be a deterministic Python component,
- FR-10 (FR): The check must support Python, TypeScript, Go, and Rust, scoped to the new
- AC-2 (AC): A new test sharing a file with an unrelated pre-existing failure is still
- AC-3 (AC): `build-ticket.md` Step 4 instructs writing tests, gating red, writing
- AC-4 (AC): Step 4e's gate, repair loop, and `MAX_REPAIR_ATTEMPTS` are unchanged.
