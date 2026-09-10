"""Content-verification for ticket 0081's `Panels:` field in critic-brief.md.

Asserts Step 1 gained the optional `Panels:` field (skip self-detection, fixed
and complete active set, no self-activation), pinned the exact `Panels active:`
announcement format for every invocation, and documents Secondary-panel
escalation as manual-only — while every pre-existing Step 1 behaviour and the
severity/anti-pattern sections stay intact.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CRITIC = (_ROOT / "context" / "critic-brief.md").read_text(encoding="utf-8")

ANNOUNCEMENT_FORMAT = "Panels active: <Name>[, <Name>...]"


def _section(doc: str, start_marker: str, end_marker: str) -> str:
    start = doc.index(start_marker)
    end = doc.index(end_marker, start + len(start_marker))
    return doc[start:end]


def _step_1() -> str:
    return _section(_CRITIC, "## Step 1", "## Step 2")


# --- FR-5: the optional `Panels:` field ---------------------------------------


def test_step_1_documents_the_optional_panels_field() -> None:
    step_1 = _step_1()
    assert "`Panels: <name>[, <name>...]`" in step_1
    assert "optional" in step_1.lower()


def test_panels_field_makes_the_agent_skip_its_own_panel_detection() -> None:
    lowered = _step_1().lower()
    assert "skip" in lowered
    assert "panel_detect.py" in lowered
    assert "fixed and complete" in lowered


def test_panels_field_forbids_self_activating_another_panel() -> None:
    lowered = _step_1().lower()
    assert "do not self-activate" in lowered
    assert "reviews only the named panel(s)" in lowered


def test_panels_field_overrides_cores_always_active_default() -> None:
    step_1 = _step_1()
    assert "The field overrides Core's always-active default." in step_1
    assert "Load `core.md` only when the field names `Core`." in step_1
    assert "A `Panels: Python` agent does not read `core.md`" in step_1


def test_core_is_only_unconditionally_active_absent_a_panels_field() -> None:
    step_1 = _step_1()
    assert "**unless a `Panels:` field is present**" in step_1
    assert "Core is active only when the field names it" in step_1
    assert "Absent a `Panels:` field, Core is always among them." in step_1


def test_panels_field_absence_leaves_step_1_unchanged() -> None:
    lowered = _step_1().lower()
    assert "when the field is absent" in lowered
    assert "unchanged" in lowered


# --- FR-6: the pinned announcement format ------------------------------------


def test_step_1_pins_the_exact_panels_active_announcement_format() -> None:
    step_1 = _step_1()
    assert ANNOUNCEMENT_FORMAT in step_1
    assert "comma-separated" in step_1.lower()


def test_announcement_format_applies_to_every_invocation() -> None:
    lowered = _step_1().lower()
    assert "every critic invocation" in lowered
    assert "self-detected" in lowered


def test_announcement_format_names_the_orchestrator_verification_it_serves() -> None:
    step_1 = _step_1()
    assert "commands/problem.md" in step_1
    assert "verif" in step_1.lower()


# --- FR-11: Secondary escalation stays manual --------------------------------


def test_secondary_panel_escalation_is_documented_as_manual_only() -> None:
    step_1 = _step_1()
    lowered = step_1.lower()
    assert "secondary" in lowered
    assert "never automatic" in lowered
    assert "fan-out" in lowered
    assert "merged reports" in lowered


# --- NFR-1: additive only ----------------------------------------------------


def test_pre_existing_step_1_instructions_survive() -> None:
    step_1 = _step_1()
    assert "context/panels/core.md" in step_1
    assert "It is always active" in step_1
    assert "--design" in step_1
    assert "For each entry in `candidates`, disposition it (activate or defer) with a one-line reason." in step_1
    assert "Read only the panel files for active panels." in step_1


def test_incremental_round_branches_survive() -> None:
    assert "Mode: incremental" in _CRITIC
    step_2_5 = _section(_CRITIC, "## Step 2.5", "## Step 3")
    assert "skip requirements coverage and solution alignment" in step_2_5.lower()


def test_finding_header_format_and_anti_patterns_survive() -> None:
    assert "**SEVERITY** · <Panel> / <Dimension> · `<file>:<line>`" in _CRITIC
    anti = _section(_CRITIC, "## Anti-patterns", "- Findings derived from")
    assert "Findings without file:line references" in anti
    assert "Re-flagging gate-covered issues" in anti
