"""Content-verification test for ticket 0062's repair-escalation.md wiring.

FR-5 requires every round's findings to carry the hidden key marker, round 1
onward — including escalation rounds (repair-escalation.md Phase 1 and Phase 2
continue the same round-numbering sequence into the same critic-findings.md).
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
ESCALATION = ROOT / "context" / "flows" / "repair-escalation.md"


def _phase_text(start_header: str, end_header: str | None = None) -> str:
    text = ESCALATION.read_text()
    start = text.index(start_header)
    end = text.index(end_header, start) if end_header else len(text)
    return text[start:end]


def test_phase1_embeds_marker_and_reconciles():
    section = _phase_text("## Phase 1", "## Phase 2")
    assert "marker_for_key" in section
    assert "finding_key" in section
    assert "parse_critic_findings" in section
    assert "latest_section" in section
    assert "reconcile(" in section


def test_phase1_diagnosis_is_a_level3_heading_not_shadowing_latest_section():
    """The diagnosis is persisted before Phase 1's critic-round reconcile call; a
    `## `-level heading would make `latest_section()` see it instead of the real
    prior round, harvesting an empty `prev` every escalation (round-3 regression)."""
    section = _phase_text("## Phase 1", "## Phase 2")
    assert re.search(r"^\s*### Escalation diagnosis", section, re.MULTILINE)
    assert not re.search(r"^\s*## Escalation diagnosis", section, re.MULTILINE)


def test_phase2_embeds_marker_and_reconciles():
    section = _phase_text("## Phase 2")
    assert "marker_for_key" in section
    assert "finding_key" in section
    assert "parse_critic_findings" in section
    assert "latest_section" in section
    assert "reconcile(" in section
