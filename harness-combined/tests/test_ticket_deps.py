"""Tests for ticket_deps.py — dependency parsing, cycle detection, layering, Mermaid."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from ticket_deps import (
    MERMAID_UNSAFE_CHARS,
    TicketCyclicDependencyError,
    TicketGraph,
    TicketInfo,
    assert_acyclic,
    assert_acyclic_with_proposed,
    blocking_dependencies,
    build_graph,
    check_cycle,
    load_ticket_statuses,
    mermaid_diagram,
    normalize_ticket_number,
    parse_deps,
    topo_layers,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _info(number: str, *, status: str = "solution", title: str = "", deps=()):
    return TicketInfo(
        number=number, status=status, title=title, depends_on=tuple(deps)
    )


def _write_ticket(root: Path, number: str, *, status: str, deps: str | None = None,
                  title: str = "T", completed: bool = False) -> None:
    base = root / "completed" if completed else root
    tdir = base / f"{number}-slug"
    tdir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"status: {status}",
        f"ticket: {number}",
        f"title: {title}",
        f"branch: ticket/{number}-slug",
    ]
    if deps is not None:
        lines.append(f"depends-on: {deps}")
    (tdir / "status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# FR-1 / FR-2 — depends-on parsing
# --------------------------------------------------------------------------- #

def test_build_graph_records_declared_deps():
    infos = {
        "0010": _info("0010", status="done"),
        "0011": _info("0011", status="done"),
        "0032": _info("0032", deps=["0010", "0011"]),
    }
    graph = build_graph(infos)
    assert ("0010", "0032") in graph.edges
    assert ("0011", "0032") in graph.edges
    assert len(graph.edges) == 2


def test_absent_depends_on_is_empty():
    infos = {"0032": _info("0032")}
    graph = build_graph(infos)
    assert graph.edges == ()
    assert graph.nodes["0032"].depends_on == ()


def test_normalize_ticket_number():
    assert normalize_ticket_number("10") == "0010"
    assert normalize_ticket_number("0032") == "0032"
    assert normalize_ticket_number("0032-ticket-dependency-dag") == "0032"
    assert normalize_ticket_number("12345") == "12345"
    with pytest.raises(ValueError):
        normalize_ticket_number("no-digits")


# --------------------------------------------------------------------------- #
# FR-9 — unknown reference validation
# --------------------------------------------------------------------------- #

def test_build_graph_unknown_dep_raises_naming_ticket():
    infos = {"0032": _info("0032", deps=["9999"])}
    with pytest.raises(ValueError) as exc:
        build_graph(infos)
    assert "0032" in str(exc.value)
    assert "9999" in str(exc.value)


# --------------------------------------------------------------------------- #
# FR-7 — cycle detection
# --------------------------------------------------------------------------- #

def test_check_cycle_clean_returns_none():
    infos = {
        "0001": _info("0001", status="done"),
        "0002": _info("0002", deps=["0001"]),
        "0003": _info("0003", deps=["0002"]),
    }
    assert check_cycle(build_graph(infos)) is None


def test_check_cycle_two_node_cycle():
    infos = {
        "0001": _info("0001", deps=["0002"]),
        "0002": _info("0002", deps=["0001"]),
    }
    cycle = check_cycle(build_graph(infos))
    assert cycle is not None
    assert cycle[0] == cycle[-1]  # repeated endpoint
    assert set(cycle) == {"0001", "0002"}


def test_check_cycle_three_node_cycle():
    infos = {
        "0001": _info("0001", deps=["0003"]),
        "0002": _info("0002", deps=["0001"]),
        "0003": _info("0003", deps=["0002"]),
    }
    cycle = check_cycle(build_graph(infos))
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert {"0001", "0002", "0003"} <= set(cycle)


def test_assert_acyclic_raises_named_cycle():
    infos = {
        "0001": _info("0001", deps=["0002"]),
        "0002": _info("0002", deps=["0001"]),
    }
    graph = build_graph(infos)
    with pytest.raises(TicketCyclicDependencyError) as exc:
        assert_acyclic(graph)
    assert "0001" in str(exc.value)
    assert "0002" in str(exc.value)


def test_assert_acyclic_noop_on_clean_graph():
    infos = {"0001": _info("0001"), "0002": _info("0002", deps=["0001"])}
    assert_acyclic(build_graph(infos))  # must not raise


# --------------------------------------------------------------------------- #
# FR-4 / FR-5 — topological layering
# --------------------------------------------------------------------------- #

def test_topo_layers_diamond():
    # 0001 -> {0002, 0003} -> 0004
    infos = {
        "0001": _info("0001"),
        "0002": _info("0002", deps=["0001"]),
        "0003": _info("0003", deps=["0001"]),
        "0004": _info("0004", deps=["0002", "0003"]),
    }
    layers = topo_layers(build_graph(infos))
    assert layers == [["0001"], ["0002", "0003"], ["0004"]]


def test_topo_layers_independent_nodes_single_wave():
    infos = {"0001": _info("0001"), "0002": _info("0002")}
    assert topo_layers(build_graph(infos)) == [["0001", "0002"]]


def test_topo_layers_raises_on_cycle():
    infos = {
        "0001": _info("0001", deps=["0002"]),
        "0002": _info("0002", deps=["0001"]),
    }
    with pytest.raises(TicketCyclicDependencyError):
        topo_layers(build_graph(infos))


# --------------------------------------------------------------------------- #
# FR-6 — Mermaid diagram
# --------------------------------------------------------------------------- #

def test_mermaid_starts_with_graph_td_and_has_edges():
    infos = {
        "0010": _info("0010", status="done", title="Base"),
        "0032": _info("0032", title="Dependent", deps=["0010"]),
    }
    out = mermaid_diagram(build_graph(infos))
    assert out.startswith("graph TD")
    assert "0010 --> 0032" in out


def test_mermaid_strips_unsafe_chars_from_labels():
    infos = {
        # Include a double-quote: the label is emitted in Mermaid's ["..."] form,
        # so an unstripped " would close the label early and break the diagram.
        "0032": _info("0032", title='DAG (viz): [colon] {brace} |pipe| "quote"'),
    }
    out = mermaid_diagram(build_graph(infos))
    # Locate the node line `    0032["<label>"]` and extract the inner label text
    # (between the syntactic [" and "]), then assert no unsafe char survives in it.
    label_line = next(line for line in out.splitlines() if line.strip().startswith("0032["))
    label_body = label_line.split('["', 1)[1].rsplit('"]', 1)[0]
    for ch in MERMAID_UNSAFE_CHARS:
        assert ch not in label_body


# --------------------------------------------------------------------------- #
# FR-3 — blocking dependencies
# --------------------------------------------------------------------------- #

def test_blocking_dependencies_flags_non_done():
    infos = {
        "0010": _info("0010", status="implementing"),
        "0011": _info("0011", status="done"),
        "0032": _info("0032", deps=["0010", "0011"]),
    }
    blocked = blocking_dependencies(build_graph(infos), "0032")
    numbers = {b.number for b in blocked}
    assert numbers == {"0010"}
    assert blocked[0].status == "implementing"


def test_blocking_dependencies_all_done_is_empty():
    infos = {
        "0010": _info("0010", status="done"),
        "0032": _info("0032", deps=["0010"]),
    }
    assert blocking_dependencies(build_graph(infos), "0032") == []


# --------------------------------------------------------------------------- #
# Path containment (fail-closed) + I/O layer
# --------------------------------------------------------------------------- #

def test_load_ticket_statuses_reads_deps(tmp_path: Path):
    root = tmp_path / ".tickets"
    _write_ticket(root, "0010", status="done")
    _write_ticket(root, "0032", status="solution", deps="0010")
    infos = load_ticket_statuses(root)
    assert set(infos) == {"0010", "0032"}
    assert infos["0032"].depends_on == ("0010",)
    assert infos["0010"].status == "done"


def test_load_finds_completed_dependency(tmp_path: Path):
    # FR-8: dependency lives in .tickets/completed/
    root = tmp_path / ".tickets"
    _write_ticket(root, "0010", status="done", completed=True)
    _write_ticket(root, "0032", status="solution", deps="0010")
    graph = parse_deps(root)
    assert "0010" in graph.nodes
    assert ("0010", "0032") in graph.edges
    assert check_cycle(graph) is None


def test_parse_deps_unknown_ref_raises(tmp_path: Path):
    root = tmp_path / ".tickets"
    _write_ticket(root, "0032", status="solution", deps="7777")
    with pytest.raises(ValueError) as exc:
        parse_deps(root)
    assert "7777" in str(exc.value)


def test_load_ticket_statuses_containment_guard(tmp_path: Path):
    # A ticket dir that is a symlink escaping the tickets root must raise
    # BEFORE the status file is opened.
    root = tmp_path / ".tickets"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "status.md").write_text("status: done\nticket: 0099\n", encoding="utf-8")
    link = root / "0099-evil"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    with pytest.raises(ValueError):
        load_ticket_statuses(root)


def test_load_missing_root_returns_empty(tmp_path: Path):
    assert load_ticket_statuses(tmp_path / "does-not-exist") == {}


# --------------------------------------------------------------------------- #
# FR-3 / FR-5 — I/O -> graph seam via parse_deps (integration)
# --------------------------------------------------------------------------- #

def test_blocking_dependencies_via_parse_deps(tmp_path: Path):
    # FR-3: /build blocks when a dependency is not yet `done`, driven through the
    # real filesystem -> parse_deps -> blocking_dependencies seam.
    root = tmp_path / ".tickets"
    _write_ticket(root, "0010", status="implementing")
    _write_ticket(root, "0011", status="done", completed=True)
    _write_ticket(root, "0032", status="solution", deps="0010, 0011")
    graph = parse_deps(root)
    blocked = blocking_dependencies(graph, "0032")
    assert {b.number for b in blocked} == {"0010"}
    assert blocked[0].status == "implementing"


def test_topo_layers_via_parse_deps(tmp_path: Path):
    # FR-5: wave order rendered from real status.md files.
    root = tmp_path / ".tickets"
    _write_ticket(root, "0010", status="done")
    _write_ticket(root, "0011", status="solution", deps="0010")
    _write_ticket(root, "0012", status="solution", deps="0011")
    assert topo_layers(parse_deps(root)) == [["0010"], ["0011"], ["0012"]]


# --------------------------------------------------------------------------- #
# FR-7 / FR-9 — write-time proposed-edge guard (assert_acyclic_with_proposed)
# --------------------------------------------------------------------------- #

def test_proposed_edge_cycle_rejected(tmp_path: Path):
    # 0010 already depends on 0032 on disk; the ticket now being written (0032)
    # proposes depends-on: 0010 -> a cycle that only exists once the edge is added.
    root = tmp_path / ".tickets"
    _write_ticket(root, "0010", status="solution", deps="0032")
    _write_ticket(root, "0032", status="solution")  # no depends-on yet on disk
    proposed = TicketInfo(number="0032", status="solution", depends_on=("0010",))
    with pytest.raises(TicketCyclicDependencyError) as exc:
        assert_acyclic_with_proposed(root, proposed)
    assert "0010" in str(exc.value)
    assert "0032" in str(exc.value)


def test_proposed_edge_unknown_ref_rejected(tmp_path: Path):
    root = tmp_path / ".tickets"
    _write_ticket(root, "0032", status="solution")
    proposed = TicketInfo(number="0032", status="solution", depends_on=("9999",))
    with pytest.raises(ValueError) as exc:
        assert_acyclic_with_proposed(root, proposed)
    assert "9999" in str(exc.value)


def test_proposed_edge_valid_accepted(tmp_path: Path):
    root = tmp_path / ".tickets"
    _write_ticket(root, "0010", status="done", completed=True)
    _write_ticket(root, "0032", status="solution")
    proposed = TicketInfo(number="0032", status="solution", depends_on=("0010",))
    graph = assert_acyclic_with_proposed(root, proposed)  # must not raise
    assert ("0010", "0032") in graph.edges


def test_proposed_edge_normalizes_non_padded_inputs(tmp_path: Path):
    # A caller passing bare "32"/"10" must collide with on-disk 4-digit nodes,
    # not create an orphan node or a spurious unknown-ref error.
    root = tmp_path / ".tickets"
    _write_ticket(root, "0010", status="done", completed=True)
    _write_ticket(root, "0032", status="solution")
    proposed = TicketInfo(number="32", status="solution", depends_on=("10",))
    graph = assert_acyclic_with_proposed(root, proposed)
    assert ("0010", "0032") in graph.edges
    assert "0032" in graph.nodes and "32" not in graph.nodes


# --------------------------------------------------------------------------- #
# NFR-1 — performance on a 200-node graph
# --------------------------------------------------------------------------- #

def test_cycle_and_topo_perf_200_nodes():
    # Build a 200-node chain-plus-fan DAG.
    infos: dict[str, TicketInfo] = {}
    numbers = [str(i).zfill(4) for i in range(1, 201)]
    for idx, num in enumerate(numbers):
        deps = [numbers[idx - 1]] if idx > 0 else []
        infos[num] = _info(num, deps=deps)
    graph = build_graph(infos)

    best = min(
        _time_once(graph) for _ in range(5)
    )
    # NFR-1 target is < 50 ms; assert a generous non-flaky ceiling.
    assert best < 0.05, f"cycle+topo took {best * 1000:.2f} ms (target < 50 ms)"


def _time_once(graph: TicketGraph) -> float:
    start = time.perf_counter()
    assert check_cycle(graph) is None
    topo_layers(graph)
    return time.perf_counter() - start
