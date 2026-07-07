"""
Verification tests for ticket 0042 — Persist critic findings and escalation
diagnoses; record failures to memory.

Two kinds of check:
  * Docs-grep — the five flow/skill wiring points (FR-1, FR-2, FR-4, FR-5) plus
    the critic-findings.md convention documented in harness-reference.md.
  * Memory round-trip (FR-3) — memory.py accepts a gate "critic" / outcome
    "escalated" record and retrieval surfaces it for similar error text.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
FLOWS = ROOT / "context" / "flows"
BUILD = FLOWS / "build-ticket.md"
ESCALATION = FLOWS / "repair-escalation.md"
DELIVER = FLOWS / "deliver-ticket.md"
REFERENCE = ROOT / "context" / "harness-reference.md"
REVIEW = ROOT / "skills" / "review" / "SKILL.md"
DEBUG = ROOT / "skills" / "debug" / "SKILL.md"
PARSE_HELPER = ROOT / "context" / "helpers" / "parse-gate-findings.md"


def _section(content: str, start_header: str, end_header: str | None = None) -> str:
    """Return the text from start_header up to end_header (or EOF)."""
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


# --- FR-1: build-ticket.md Step 7 + each repair round append to critic-findings.md ---

def test_build_step7_appends_report_to_critic_findings():
    content = BUILD.read_text()
    step7 = _section(content, "## Step 7 — Spawn post-build critic", "### Step 7a")
    assert "critic-findings.md" in step7, \
        "Step 7 must append the critic report to critic-findings.md"
    lower = step7.lower()
    assert "append" in lower, "Step 7 must instruct appending the report"
    assert "round" in lower and "date" in lower, \
        "Step 7 round section must be headed by round number and date"
    assert "commit" in lower, "Step 7 must commit the critic-findings.md on the branch"


def test_build_repair_round_appends_to_critic_findings():
    content = BUILD.read_text()
    step7a = _section(content, "### Step 7a", "### Step 7b")
    assert "critic-findings.md" in step7a, \
        "Each repair round (Step 7a) must append its critic report to critic-findings.md"


# --- FR-3 wiring: build-ticket.md Step 4e records outcome "escalated" ---

def test_build_step4e_records_escalated_outcome():
    content = BUILD.read_text()
    step4 = _section(content, "## Step 4 — Execute each spec", "## Step 5")
    assert 'outcome="passed"' in step4, "Step 4e must keep the existing passed record"
    assert 'outcome="escalated"' in step4, \
        "Step 4e must record outcome \"escalated\" when the gate loop exhausts MAX_REPAIR_ATTEMPTS"


# --- FR-2: repair-escalation.md persists diagnosis + records memory (gate "critic") ---

def test_escalation_persists_diagnosis_to_critic_findings():
    content = ESCALATION.read_text()
    assert "critic-findings.md" in content, \
        "repair-escalation.md must append the Phase 1 diagnosis to critic-findings.md"
    lower = content.lower()
    assert "root cause" in lower and "fix strategy" in lower and "target location" in lower, \
        "The persisted diagnosis must include root cause, fix strategy, and target locations"


def test_escalation_records_memory_with_critic_gate():
    content = ESCALATION.read_text()
    assert 'memory(action="record"' in content, \
        "repair-escalation.md must record the diagnosis via memory(action=\"record\")"
    assert 'gate="critic"' in content, \
        "repair-escalation.md must record under gate \"critic\""


def test_escalation_persists_respawned_critic_rounds_both_phases():
    """MAJOR-1: the critic rounds re-spawned inside Phase 1 and Phase 2 must also be
    appended to critic-findings.md — every critic round is persisted, not only the
    build-loop rounds."""
    content = ESCALATION.read_text()
    phase1 = _section(content, "## Phase 1", "## Phase 2")
    phase2 = _section(content, "## Phase 2")
    for phase_name, phase in (("Phase 1", phase1), ("Phase 2", phase2)):
        assert "critic-findings.md" in phase, \
            f"repair-escalation.md {phase_name} must append its re-spawned critic round to critic-findings.md"
        assert "Persist this round" in phase, \
            f"repair-escalation.md {phase_name} must persist the re-spawned critic round"


# --- FR-4: deliver-ticket.md Step 5 scans critic-findings.md via the critic parser ---

def test_deliver_step5_scans_critic_findings():
    content = DELIVER.read_text()
    step5 = _section(content, "## Step 5 — Candidate learnings", "## Step 6")
    assert "critic-findings.md" in step5, \
        "Deliver Step 5 must scan critic-findings.md alongside gate-findings.md"


def test_deliver_step5_uses_critic_source_kind():
    """FR-4 must extract, not just name the file: Step 5 must invoke the critic parser."""
    content = DELIVER.read_text()
    step5 = _section(content, "## Step 5 — Candidate learnings", "## Step 6")
    assert 'source_kind="critic"' in step5, \
        "Step 5 must call the helper with source_kind=\"critic\" (the gate parser returns nothing)"
    assert 'gate="critic"' in step5, \
        "Step 5 must state critic candidates are tagged gate=\"critic\""


def test_parse_helper_documents_critic_parse_path():
    """BLOCKER-1: the helper must have a critic-report parse path, not only the gate parser."""
    content = PARSE_HELPER.read_text()
    assert 'source_kind' in content, \
        "parse-gate-findings.md must accept a source_kind selector"
    assert 'critic' in content.lower(), "helper must document the critic parse path"
    # The critic path must tag records with the literal gate name "critic"
    assert 'gate' in content and '`critic`' in content, \
        "critic-parsed records must carry the literal gate name `critic`"
    # It must target BLOCKER/MAJOR findings from the round/escalation sections
    assert "Round" in content and "BLOCKER" in content and "MAJOR" in content, \
        "critic parse path must extract BLOCKER/MAJOR findings from Round/Escalation sections"


# --- FR-5: review + debug skills read critic-findings.md ---

def test_review_skill_reads_critic_findings():
    content = REVIEW.read_text()
    assert "critic-findings.md" in content, \
        "review SKILL.md must read critic-findings.md when present"


def test_debug_skill_reads_critic_findings():
    content = DEBUG.read_text()
    assert "critic-findings.md" in content, \
        "debug SKILL.md must read critic-findings.md when present"


# --- Convention documented in harness-reference.md ---

def test_reference_documents_critic_findings_convention():
    content = REFERENCE.read_text()
    assert "critic-findings.md" in content, \
        "harness-reference.md must document the critic-findings.md convention"
    # Append-only, per-round sections
    lower = content.lower()
    assert "append-only" in lower or "append only" in lower, \
        "The convention must state critic-findings.md is append-only"
    assert "per-round" in lower or "per round" in lower or "round section" in lower, \
        "The convention must describe per-round sections"


# --- FR-3: memory round-trip for gate "critic" / outcome "escalated" ---

def test_memory_records_escalated_critic_outcome_and_retrieves():
    from memory import SQLiteFailureMemory

    with tempfile.TemporaryDirectory() as d:
        mem = SQLiteFailureMemory(os.path.join(d, "memory.db"))
        errors = (
            "critic BLOCKER: requirements coverage missing — no test exercises "
            "FR-3 in handler.py:42"
        )
        mem.record(
            spec_id="0042-persist-critic-findings",
            gate="critic",
            errors_text=errors,
            attempt=3,
            outcome="escalated",
        )
        results = mem.retrieve_similar(
            errors_text="requirements coverage missing test handler",
            gate="critic",
        )
        assert results, "an escalated critic record must be retrievable for similar error text"
        joined = "\n".join(results)
        assert "escalated" in joined, "retrieval must surface the escalated outcome"
        assert "critic" in joined, "retrieval must report the critic gate"


def test_memory_critic_gate_partitions_from_other_gates():
    from memory import SQLiteFailureMemory

    with tempfile.TemporaryDirectory() as d:
        mem = SQLiteFailureMemory(os.path.join(d, "memory.db"))
        mem.record(
            spec_id="s1",
            gate="lint",
            errors_text="E501 line too long in handler.py:42",
            attempt=1,
            outcome="passed",
        )
        # A query on the critic gate must not surface the lint-gate record.
        results = mem.retrieve_similar(errors_text="line too long handler", gate="critic")
        assert results == [], "gate 'critic' retrieval must not return non-critic records"
