"""Content-verification for ticket 0040's flow/critic-brief wiring (FR-2, FR-5).

Asserts build-ticket.md Steps 4f (integration gate; relettered from 4e by
ticket 0065's test-first sub-step split) and 7a document the repair-integrity
check, and critic-brief.md Step 2.5 marks weakened/deleted tests as BLOCKER
findings.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BUILD = (_ROOT / "context" / "flows" / "build-ticket.md").read_text(encoding="utf-8")
_CRITIC = (_ROOT / "context" / "critic-brief.md").read_text(encoding="utf-8")


def _section(doc: str, start_marker: str, end_marker: str) -> str:
    start = doc.index(start_marker)
    end = doc.index(end_marker, start + len(start_marker))
    return doc[start:end]


def test_build_ticket_references_repair_integrity_module() -> None:
    assert "gates/repair_integrity.py" in _BUILD
    assert "classify_diff" in _BUILD


def test_step_4e_documents_integrity_check() -> None:
    step_4f = _section(_BUILD, "**f. Integration gate (directory mode):**", "**g. Checkpoint:**")
    assert "repair-integrity" in step_4f.lower()
    assert "restore the test" in step_4f.lower()


def test_step_7a_documents_integrity_check() -> None:
    step_7a = _section(_BUILD, "### Step 7a", "### Step 7b")
    assert "repair-integrity" in step_7a.lower()
    assert "restore the test" in step_7a.lower()


def test_critic_brief_step_2_5_flags_weakened_tests_as_blocker() -> None:
    step_2_5 = _section(_CRITIC, "## Step 2.5", "## Step 3")
    lower = step_2_5.lower()
    assert "weakened" in lower
    assert "deleted" in lower
    assert "blocker" in lower
    assert "test plan" in lower
