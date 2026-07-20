"""Content-verification test for ticket 0062's harness-reference.md update.

Asserts the "Critic findings file" section documents the new hidden per-finding
key marker and names gates/critic_reconciler.reconcile() as what build-ticket.md
calls each round, without disturbing the section's existing bullets.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
REFERENCE = ROOT / "context" / "harness-reference.md"


def _section_text() -> str:
    text = REFERENCE.read_text()
    start = text.index("### Critic findings file")
    end = text.index("\n---\n", start)
    return text[start:end]


def test_marker_documented():
    section = _section_text()
    assert "harness-finding-key" in section
    assert "finding_key" in section


def test_reconcile_named():
    section = _section_text()
    assert "reconcile()" in section or "reconcile(" in section
    assert "critic_reconciler" in section


def test_existing_bullets_still_present():
    section = _section_text()
    assert "Append-only, per-round sections." in section
    assert "Committed on the branch with each round." in section
    assert "Consumed downstream." in section
