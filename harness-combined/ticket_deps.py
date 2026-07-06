"""Ticket dependency parsing, cycle detection, topological layering, and Mermaid rendering.

Two cleanly separated layers:

* **I/O layer** — :func:`load_ticket_statuses` scans ``.tickets/`` and
  ``.tickets/completed/`` for ``status.md`` files, parses the optional
  ``depends-on:`` field, normalizes ticket numbers to 4-digit zero-padded
  strings, and contains every scanned path within the tickets root before
  opening it (fail-closed path-traversal guard).
* **Graph layer** — :func:`build_graph`, :func:`check_cycle`,
  :func:`topo_layers`, and :func:`mermaid_diagram` operate on plain in-memory
  data structures so the algorithms are testable without touching the
  filesystem. Mirrors the ``dag.py`` graph conventions used for spec DAGs.

The convenience wrapper :func:`parse_deps` composes the two layers.
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

# Characters that break a Mermaid node label (parse into edge/shape syntax on
# GitHub). Single source of truth for label sanitization — flow docs reference
# this constant by name so the LLM delegates stripping to mermaid_diagram()
# rather than re-implementing it ad hoc.
# The double-quote is included because labels are emitted in Mermaid's quoted
# form ``id["label"]`` — an embedded ``"`` closes the label early and breaks the
# whole diagram (NFR-2), so it must be stripped alongside the shape/edge chars.
MERMAID_UNSAFE_CHARS = set('()[]{}|:"')

_DEPENDS_ON_RE = re.compile(r"^\s*depends-on\s*:\s*(.*)$", re.IGNORECASE)
_STATUS_RE = re.compile(r"^\s*status\s*:\s*(.*)$", re.IGNORECASE)
_TITLE_RE = re.compile(r"^\s*title\s*:\s*(.*)$", re.IGNORECASE)
_TICKET_RE = re.compile(r"^\s*ticket\s*:\s*(.*)$", re.IGNORECASE)
_LEADING_DIGITS_RE = re.compile(r"(\d+)")

COMPLETED_SUBDIR = "completed"


class TicketCyclicDependencyError(ValueError):
    """Raised when the ticket dependency graph contains a cycle.

    Subclasses ``ValueError`` so callers can ``except`` it specifically, mirroring
    ``dag.CyclicDependencyError``. The message contains the offending cycle path,
    e.g. ``0001 -> 0002 -> 0001``.
    """


def normalize_ticket_number(raw: str) -> str:
    """Return the 4-digit zero-padded ticket number embedded in *raw*.

    Accepts a bare number (``"10"`` -> ``"0010"``), a slugged directory name
    (``"0032-ticket-dependency-dag"`` -> ``"0032"``), or an already-normalized
    value. Raises ``ValueError`` if *raw* contains no digit run.
    """
    match = _LEADING_DIGITS_RE.search(raw)
    if match is None:
        raise ValueError(f"No ticket number found in {raw!r}")
    return match.group(1).zfill(4)


@dataclass(frozen=True)
class TicketInfo:
    """A single ticket's dependency-relevant metadata, parsed from ``status.md``."""

    number: str
    status: str
    title: str = ""
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class TicketGraph:
    """Immutable ticket dependency graph.

    ``nodes`` maps normalized ticket number to :class:`TicketInfo`. ``edges`` is
    an ordered tuple of ``(dependency, dependent)`` pairs — the dependency must
    reach ``done`` before the dependent may build, so an edge points from the
    prerequisite toward the ticket that requires it (same direction ``dag.py``
    uses for spec execution layers).
    """

    nodes: Mapping[str, TicketInfo]
    edges: tuple[tuple[str, str], ...]


# --------------------------------------------------------------------------- #
# I/O layer
# --------------------------------------------------------------------------- #

def _parse_status_file(text: str, fallback_number: str) -> TicketInfo:
    """Parse ``status.md`` *text* into a :class:`TicketInfo`.

    Absence of a ``depends-on:`` line is treated identically to an empty list.
    """
    status = ""
    title = ""
    number = fallback_number
    depends_on: list[str] = []

    for line in text.splitlines():
        if (m := _STATUS_RE.match(line)) is not None:
            status = m.group(1).strip()
        elif (m := _TITLE_RE.match(line)) is not None:
            title = m.group(1).strip()
        elif (m := _TICKET_RE.match(line)) is not None:
            candidate = m.group(1).strip()
            if candidate:
                number = normalize_ticket_number(candidate)
        elif (m := _DEPENDS_ON_RE.match(line)) is not None:
            for part in m.group(1).split(","):
                part = part.strip()
                if part:
                    depends_on.append(normalize_ticket_number(part))

    return TicketInfo(
        number=number,
        status=status,
        title=title,
        depends_on=tuple(depends_on),
    )


def _iter_status_dirs(root: Path) -> list[Path]:
    """Yield ticket directories under *root* and ``root/completed`` (FR-8)."""
    dirs: list[Path] = []
    for base in (root, root / COMPLETED_SUBDIR):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and child.name != COMPLETED_SUBDIR:
                dirs.append(child)
    return dirs


def load_ticket_statuses(tickets_root: Path) -> dict[str, TicketInfo]:
    """Scan *tickets_root* (and its ``completed/`` subdir) for ``status.md`` files.

    Every candidate path is resolved and asserted to lie *within* the resolved
    tickets root before any file is opened — a fail-closed guard against path
    traversal via symlinks or crafted directory names. Ticket numbers are
    normalized to 4-digit zero-padded strings.

    Raises ``ValueError`` if a scanned path escapes the tickets root.
    """
    root = Path(tickets_root).resolve()
    if not root.is_dir():
        return {}

    infos: dict[str, TicketInfo] = {}
    for ticket_dir in _iter_status_dirs(root):
        status_file = ticket_dir / "status.md"
        resolved = status_file.resolve()
        # Containment guard: reject anything that resolves outside the root
        # BEFORE opening it.
        if not resolved.is_relative_to(root):
            raise ValueError(
                f"Refusing to read status file outside tickets root: {resolved} "
                f"escapes {root}"
            )
        if not resolved.is_file():
            continue
        number = normalize_ticket_number(ticket_dir.name)
        parsed = _parse_status_file(resolved.read_text(encoding="utf-8"), number)
        # The directory name is authoritative for the ticket number/key.
        infos[number] = TicketInfo(
            number=number,
            status=parsed.status,
            title=parsed.title,
            depends_on=parsed.depends_on,
        )
    return infos


# --------------------------------------------------------------------------- #
# Graph layer
# --------------------------------------------------------------------------- #

def build_graph(infos: Mapping[str, TicketInfo]) -> TicketGraph:
    """Build a frozen :class:`TicketGraph` from a ticket-number -> info mapping.

    Raises ``ValueError`` naming the offending ticket and reference when any
    ``depends_on`` entry points at an unknown ticket number (FR-9).
    """
    known = set(infos)
    edges: list[tuple[str, str]] = []
    for number, info in infos.items():
        for dep in info.depends_on:
            if dep not in known:
                raise ValueError(
                    f"Ticket {number} depends on unknown ticket {dep}"
                )
            edges.append((dep, number))
    # Freeze the node mapping so the graph is genuinely immutable.
    frozen_nodes: Mapping[str, TicketInfo] = MappingProxyType(dict(infos))
    return TicketGraph(nodes=frozen_nodes, edges=tuple(edges))


def _adjacency(graph: TicketGraph) -> dict[str, list[str]]:
    """dependency -> list of dependents."""
    adj: dict[str, list[str]] = defaultdict(list)
    for dep, dependent in graph.edges:
        adj[dep].append(dependent)
    return adj


def check_cycle(graph: TicketGraph) -> list[str] | None:
    """Return a cycle path if the graph has one, else ``None`` (FR-7, NFR-1).

    On a cycle, returns a non-empty list of the form ``[A, B, C, A]`` — the
    repeated endpoint makes the cycle explicit. Never returns an empty list.
    DFS with a recursion stack; O(N+E).
    """
    adj = _adjacency(graph)
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in graph.nodes}
    # Include any node that appears only as an edge endpoint (defensive).
    for dep, dependent in graph.edges:
        color.setdefault(dep, WHITE)
        color.setdefault(dependent, WHITE)

    stack_path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GREY
        stack_path.append(node)
        for nxt in adj.get(node, ()):
            if color[nxt] == GREY:
                # Found a back edge — slice the current path from nxt onward.
                idx = stack_path.index(nxt)
                return stack_path[idx:] + [nxt]
            if color[nxt] == WHITE:
                found = dfs(nxt)
                if found is not None:
                    return found
        stack_path.pop()
        color[node] = BLACK
        return None

    for start in graph.nodes:
        if color[start] == WHITE:
            found = dfs(start)
            if found is not None:
                return found
    return None


def assert_acyclic(graph: TicketGraph) -> None:
    """Raise :class:`TicketCyclicDependencyError` if *graph* contains a cycle.

    The write-time guard called by ``/problem`` Phase 4 and by ``build-ticket``
    on every ``status.md`` write. The error message names the full cycle path.
    """
    cycle = check_cycle(graph)
    if cycle is not None:
        raise TicketCyclicDependencyError(
            "Ticket dependency cycle detected: " + " -> ".join(cycle)
        )


def topo_layers(graph: TicketGraph) -> list[list[str]]:
    """Kahn topological sort into execution waves (FR-5).

    Each returned layer is a list of ticket numbers with no unmet dependencies
    once all prior layers are complete. Ticket numbers within a layer are sorted
    for deterministic output. Raises :class:`TicketCyclicDependencyError` if the
    graph is cyclic (a partial Kahn result would silently drop the cycle).
    """
    in_degree: dict[str, int] = {n: 0 for n in graph.nodes}
    dependents: dict[str, list[str]] = defaultdict(list)
    for dep, dependent in graph.edges:
        in_degree[dependent] = in_degree.get(dependent, 0) + 1
        in_degree.setdefault(dep, in_degree.get(dep, 0))
        dependents[dep].append(dependent)

    queue: deque[str] = deque(sorted(n for n, deg in in_degree.items() if deg == 0))
    layers: list[list[str]] = []
    emitted = 0

    while queue:
        layer: list[str] = []
        for _ in range(len(queue)):
            node = queue.popleft()
            layer.append(node)
            emitted += 1
            for child in dependents[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        layer.sort()
        # Re-sort the next batch for deterministic wave ordering.
        queue = deque(sorted(queue))
        layers.append(layer)

    if emitted != len(in_degree):
        # Unprocessed nodes ⇒ a cycle; surface it with the full path.
        assert_acyclic(graph)
    return layers


def _sanitize_label(text: str) -> str:
    """Strip every :data:`MERMAID_UNSAFE_CHARS` character from *text*."""
    return "".join(ch for ch in text if ch not in MERMAID_UNSAFE_CHARS).strip()


def mermaid_diagram(graph: TicketGraph) -> str:
    """Render *graph* as a Mermaid ``graph TD`` diagram (FR-6, NFR-2).

    Emits a labeled node per ticket (label sanitized via
    :data:`MERMAID_UNSAFE_CHARS`) and one ``dependency --> dependent`` edge per
    declared dependency. Renders in GitHub Markdown and standard Mermaid viewers.
    """
    lines = ["graph TD"]
    for number in sorted(graph.nodes):
        info = graph.nodes[number]
        label_text = f"{number} {info.title}".strip() if info.title else number
        label = _sanitize_label(label_text)
        lines.append(f'    {number}["{label}"]')
    for dep, dependent in graph.edges:
        lines.append(f"    {dep} --> {dependent}")
    return "\n".join(lines)


def blocking_dependencies(
    graph: TicketGraph, ticket_number: str, *, done_status: str = "done"
) -> list[TicketInfo]:
    """Return the dependencies of *ticket_number* not yet in *done_status* (FR-3).

    ``build-ticket`` calls this before creating a worktree; a non-empty result
    means the build is blocked and each returned :class:`TicketInfo` names a
    blocking ticket and its current status.
    """
    number = normalize_ticket_number(ticket_number)
    info = graph.nodes.get(number)
    if info is None:
        return []
    blocked: list[TicketInfo] = []
    for dep in info.depends_on:
        dep_info = graph.nodes.get(dep)
        if dep_info is None or dep_info.status != done_status:
            blocked.append(
                dep_info
                if dep_info is not None
                else TicketInfo(number=dep, status="missing")
            )
    return blocked


# --------------------------------------------------------------------------- #
# Convenience wrapper
# --------------------------------------------------------------------------- #

def parse_deps(tickets_root: Path) -> TicketGraph:
    """Load ticket statuses from *tickets_root* and build the dependency graph."""
    return build_graph(load_ticket_statuses(tickets_root))


def assert_acyclic_with_proposed(
    tickets_root: Path, proposed: TicketInfo
) -> TicketGraph:
    """Validate a *proposed* ticket's ``depends-on:`` edges *before* they are persisted.

    The write-time guard for ``/problem`` Phase 4 — the one site that actually
    authors a ``depends-on:`` field. Running :func:`assert_acyclic` against
    :func:`parse_deps` alone would read pre-write disk state, so the edge being
    written (and any cycle or unknown reference it introduces) would be invisible.
    This overlays *proposed* onto the loaded infos, then builds and checks the
    graph, so both FR-7 (cycle) and FR-9 (unknown reference) are enforced against
    the about-to-be-written dependencies.

    Raises ``ValueError`` if *proposed* references an unknown ticket, or
    :class:`TicketCyclicDependencyError` if it forms a cycle. Returns the
    validated graph on success.
    """
    # Normalize the proposed ticket to the same 4-digit form the I/O layer uses,
    # so a caller passing "32"/"10" collides with on-disk "0032"/"0010" nodes
    # rather than producing an orphan node or a spurious unknown-ref error.
    normalized = TicketInfo(
        number=normalize_ticket_number(proposed.number),
        status=proposed.status,
        title=proposed.title,
        depends_on=tuple(normalize_ticket_number(d) for d in proposed.depends_on),
    )
    infos = load_ticket_statuses(tickets_root)
    infos[normalized.number] = normalized
    graph = build_graph(infos)  # FR-9: unknown-ref (incl. proposed's deps) -> ValueError
    assert_acyclic(graph)       # FR-7: cycle -> TicketCyclicDependencyError
    return graph
