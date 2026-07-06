"""Content-verification tests for the ticket-dependency doc wiring (ticket 0032).

The flow/command docs are LLM instruction files, so these tests pin the required
prose: each doc must reference the ticket_deps.py functions by name so the model
delegates to the Python module rather than re-implementing graph logic ad hoc.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_harness_reference_documents_depends_on():
    text = _read("context/harness-reference.md")
    assert "depends-on:" in text
    # Described as a comma-separated list of 4-digit ticket numbers.
    assert "comma-separated" in text
    assert "four-digit" in text or "4-digit" in text
    # Delegation targets named.
    assert "ticket_deps.py" in text
    assert "parse_deps" in text
    assert "check_cycle" in text


def test_build_ticket_flow_has_precondition_and_cycle_check():
    text = _read("context/flows/build-ticket.md")
    # Precondition runs before worktree creation.
    assert "before the worktree is created" in text.lower() or \
        "before worktree creation" in text.lower()
    assert "blocking_dependencies" in text
    assert "parse_deps" in text
    # Full-graph cycle check on status.md writes.
    assert "assert_acyclic" in text
    assert "TicketCyclicDependencyError" in text
    assert "cycle check" in text.lower()


def test_problem_phase4_has_cycle_check():
    text = _read("commands/problem.md")
    # Must validate the proposed edge (pre-write), not just on-disk state.
    assert "assert_acyclic_with_proposed" in text
    assert "TicketCyclicDependencyError" in text
    # Anchored to the status: solution write.
    assert "status: solution" in text


def test_ticket_status_has_dependency_graph_section():
    text = _read("commands/ticket-status.md")
    assert "Dependency Graph" in text
    assert "parse_deps" in text
    assert "mermaid_diagram" in text
    assert "topo_layers" in text
    # A Mermaid graph TD block is present.
    assert "```mermaid" in text
    assert "graph TD" in text
