# Solution

**Ticket**: 0013
**Title**: Ticket dependency field and DAG visualization

## Approach

Add a `depends-on:` field to `status.md` and introduce a `ticket_deps.py` module with cleanly separated I/O and graph-logic layers. Update `build-ticket.md` and `problem.md` (Phase 4) to enforce dependency preconditions and run a full-graph cycle check on every `status.md` write. Update `ticket-status.md` to render the dependency graph. The I/O layer resolves and contains all paths within the harness project root before any filesystem access. Cycle detection raises a named `TicketCyclicDependencyError`; unknown refs raise `ValueError`.

## Components

| Component | Responsibility | Key Interfaces |
|---|---|---|
| `ticket_deps.py` — I/O layer | Resolve `tickets_root`, assert each scanned path is contained within it (path traversal guard); scan both `.tickets/` and `.tickets/completed/`; normalize ticket numbers to 4-digit zero-padded strings | `load_ticket_statuses(tickets_root: Path) -> dict[str, TicketInfo]` |
| `ticket_deps.py` — graph layer | Build adjacency graph from `TicketInfo` dict; validate unknown refs (raise `ValueError`); DFS cycle detection (raise `TicketCyclicDependencyError` with cycle path `[A,B,C,A]` in message); Kahn topological sort to layers; Mermaid generation with `MERMAID_UNSAFE_CHARS = set("()[]{}|:")` label sanitization | `build_graph(infos) -> TicketGraph` (frozen dataclass); `check_cycle(graph) -> list[str] | None` (clean → `None`; cycle → non-empty `[A,B,C,A]` list; empty list never returned); `topo_layers(graph) -> list[list[str]]`; `mermaid_diagram(graph) -> str` |
| `ticket_deps.py` — convenience | Thin wrapper: `load_ticket_statuses` → `build_graph` | `parse_deps(tickets_root: Path) -> TicketGraph` |
| `status.md` format | New optional `depends-on:` line; format: `depends-on: XXXX, YYYY`; absence treated as empty | Parsed by `ticket_deps.py` I/O layer |
| `context/flows/build-ticket.md` | Dependency precondition check (before worktree creation); full-graph cycle check on every `status.md` write | Calls `parse_deps`; raises `TicketCyclicDependencyError` or blocks with named-dep error |
| `commands/problem.md` (Phase 4) | Full-graph cycle check when writing `status: solution` (the first write that may include a `depends-on:` field) | Same `check_cycle` call; same `TicketCyclicDependencyError` |
| `commands/ticket-status.md` | After reading all status files, call `parse_deps`; add "Dependency Graph" section with Mermaid `graph TD` block and execution-order waves | Delegates all graph ops to `ticket_deps.py` |
| `tests/test_ticket_deps.py` | Unit tests (in-memory `build_graph`) + integration tests (`tmp_path` fixtures) + content-verification tests | pytest |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Split I/O / graph layers | Graph algorithms testable with in-memory dicts; I/O path tested separately; no `pathlib` mock-patching |
| `@dataclass(frozen=True)` for `TicketGraph` | Prevents shared-state bugs; mutable construction via plain dict, freeze at `build_graph` return |
| Named `TicketCyclicDependencyError(ValueError)` | Consistent with existing `CyclicDependencyError` in `dag.py`; callers can `except` specifically; domain event not a string |
| Path containment in `load_ticket_statuses` | Fail-closed against path-traversal via crafted `depends-on:` values; mirrors `pre_write_guard.py` principle |
| Full-graph cycle check on every `status.md` write | Catches cycles introduced by editing any ticket's `depends-on:` after a dependent ticket was already written |
| Mermaid `graph TD` with `MERMAID_UNSAFE_CHARS` constant | Single source of truth for label sanitization; prevents silent parse errors on GitHub |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1, FR-2  | Unit        | `build_graph` with `depends-on: 0010, 0011`; absent field → empty deps |
| FR-3 blocking | Integration | Fixture: dep in `implementing`; assert no worktree created, error names dep |
| FR-3 success  | Integration | Fixture: dep in `done` in `.tickets/completed/`; assert build proceeds |
| FR-4, FR-5  | Unit + Integration | `topo_layers` wave order in-memory; `tmp_path` fixture → `parse_deps` returns correct layers |
| FR-6 | Unit + Content-verification | `mermaid_diagram` starts with `graph TD`, edges correct, `MERMAID_UNSAFE_CHARS` stripped; `commands/ticket-status.md` mentions `parse_deps` and Mermaid section |
| FR-7 | Unit | `check_cycle(clean) is None`; cycle A→B→A raises `TicketCyclicDependencyError` with `[A,B,A]` in message; A→B→C→A detected |
| FR-8 | Integration | Dep in `.tickets/completed/` → graph built, no error; dep absent from both dirs → `ValueError` naming ticket |
| FR-9 | Unit + Integration | `build_graph` with unknown dep → `ValueError` naming ticket; `parse_deps` on `tmp_path` fixture with bad ref → same `ValueError` |
| Path containment | Unit | `load_ticket_statuses` with path outside project root → `ValueError` before any file is opened |
| NFR-1 | Unit | `check_cycle` + `topo_layers` on 200-node graph complete in < 50 ms |

## Tradeoffs

- **Chose command-doc-level enforcement**: The harness orchestration is LLM-driven from flow docs; Python provides the logic, docs call it. Consistent with `dag.py` pattern.
- **Full-graph cycle check on every write**: One O(N+E) traversal per status transition — microseconds at N ≤ 100. Accepted for fail-closed correctness.
- **`commands/problem.md` Phase 4 is updated**: Touching a core command file adds scope, but FR-7 requires write-time cycle detection at `/problem` Phase 4; omitting this would leave a gap.

## Risks

- Pre-existing `status.md` files have no `depends-on:` — parser treats absence as empty. No migration needed.
- `commands/problem.md` and `context/flows/build-ticket.md` are both LLM instruction files — cycle-check logic must be described precisely. Content-verification tests pin the required prose.
- Mermaid label sanitization is a named constant in `ticket_deps.py`; flow doc prose must reference it so the LLM uses the Python function, not ad-hoc stripping.

## Implementation Order

1. Write `ticket_deps.py`: `TicketInfo`, `TicketCyclicDependencyError`, `load_ticket_statuses` (with path containment guard), `build_graph` (frozen `TicketGraph`), `check_cycle`, `topo_layers`, `mermaid_diagram` (uses `MERMAID_UNSAFE_CHARS`), `parse_deps`.
2. Write `tests/test_ticket_deps.py` unit tests: FR-1, FR-2, FR-4, FR-6, FR-7, FR-9, path containment, NFR-1.
3. Write `tests/test_ticket_deps.py` integration tests: FR-3 blocking, FR-3 success, FR-5, FR-8, FR-9 integration.
4. Update `context/harness-reference.md`: add `depends-on:` to `status.md` format; document semantics and normalization rule.
5. Update `context/flows/build-ticket.md`: add dep precondition check before worktree creation; add full-graph cycle check on every `status.md` write.
6. Update `commands/problem.md` (Phase 4): add full-graph cycle check when writing `status: solution`.
7. Update `commands/ticket-status.md`: add Dependency Graph section (Mermaid block + execution-order waves calling `parse_deps`).
8. Write content-verification tests for steps 5–7 (assert docs contain required prose / section markers).
