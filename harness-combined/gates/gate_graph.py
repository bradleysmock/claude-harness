"""Per-language gate dependency graphs and a cycle-detecting validator.

Directory-mode gates were historically run in a fixed sequential order. Ticket
0036 executes independent gates concurrently, so the *only* ordering that must be
preserved is a genuine data dependency: ``test`` must not run until the gate that
proves the code compiles/type-checks has passed (otherwise tests run against
type-incorrect code — the naive-parallelism risk called out in the problem
statement).

Each ``GATE_GRAPH`` maps a gate name to the list of gate names that must complete
**and pass** before it may start. Independent gates map to ``[]``. The node set is
the union of the keys and every referenced prerequisite, so a sparse graph and a
fully-enumerated one are equivalent; every gate a language actually runs is listed
here as a key for readability.

The four graphs are defined together, before any runner depends on them, to pin the
``dict[str, list[str]]`` interface the scheduler consumes.
"""

from __future__ import annotations

#: Python directory-mode gates: lint / type_check / test / security. ``test``
#: depends on ``type_check`` (don't run pytest against type-incorrect code); lint
#: and security are independent.
PYTHON_GATE_GRAPH: dict[str, list[str]] = {
    "lint": [],
    "type_check": [],
    "test": ["type_check"],
    "security": [],
}

#: TypeScript directory-mode gates: type_check / lint / test. ``test`` depends on
#: ``type_check``.
TYPESCRIPT_GATE_GRAPH: dict[str, list[str]] = {
    "type_check": [],
    "lint": [],
    "test": ["type_check"],
}

#: Go directory-mode gates: build / vet / test. ``test`` depends on ``build``;
#: ``vet`` is independent.
GO_GATE_GRAPH: dict[str, list[str]] = {
    "build": [],
    "vet": [],
    "test": ["build"],
}

#: Rust directory-mode gates: check / clippy / test. ``test`` depends on
#: ``check``; ``clippy`` is independent.
RUST_GATE_GRAPH: dict[str, list[str]] = {
    "check": [],
    "clippy": [],
    "test": ["check"],
}


def validate_dag(graph: dict[str, list[str]]) -> None:
    """Raise ``ValueError`` if ``graph`` is not a DAG (or references unknown gates).

    Cycle detection runs at call time — never during gate execution (NFR-3) — via a
    depth-first walk with a recursion stack. A prerequisite that names a gate absent
    from the graph's key set is also rejected: a graph must be self-contained so the
    scheduler can trust every declared dependency resolves.
    """
    nodes = set(graph)
    for gate, prereqs in graph.items():
        for prereq in prereqs:
            if prereq not in nodes:
                raise ValueError(
                    f"gate {gate!r} depends on unknown gate {prereq!r}"
                )

    # States: 0 = unvisited, 1 = on the current DFS stack, 2 = fully explored.
    state: dict[str, int] = {node: 0 for node in nodes}

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for prereq in graph.get(node, []):
            if state[prereq] == 1:
                cycle = " -> ".join([*path, node, prereq])
                raise ValueError(f"gate dependency cycle detected: {cycle}")
            if state[prereq] == 0:
                visit(prereq, [*path, node])
        state[node] = 2

    for node in nodes:
        if state[node] == 0:
            visit(node, [])
