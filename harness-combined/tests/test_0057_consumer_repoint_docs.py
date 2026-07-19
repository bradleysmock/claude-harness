"""Content-verification tests for ticket 0057 — panel activation moved from a
prose trigger table in skills/critique/SKILL.md to canonical TOML data in
context/panels/triggers.md, evaluated by panel_detect.py.

Reads the six named consumers (FR-10) and asserts, via structural substrings,
that each repoints to triggers.md / panel_detect.py and no longer carries the
old table or the stale "29 panels" prose.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
CRITIQUE_SKILL = ROOT / "skills" / "critique" / "SKILL.md"
REVIEW_SKILL = ROOT / "skills" / "review" / "SKILL.md"
CRITIC_BRIEF = ROOT / "context" / "critic-brief.md"
BUILD_TICKET_FLOW = ROOT / "context" / "flows" / "build-ticket.md"
README = ROOT / "README.md"
TRIGGERS = ROOT / "context" / "panels" / "triggers.md"
PANELS_DIR = ROOT / "context" / "panels"


def test_target_files_exist():
    for f in (CRITIQUE_SKILL, REVIEW_SKILL, CRITIC_BRIEF, BUILD_TICKET_FLOW, README, TRIGGERS):
        assert f.exists(), f"{f} must exist"


# --- FR-1/FR-5: triggers.md + panel_detect.py exist and are wired ---


def test_panel_detect_script_exists():
    assert (ROOT / "panel_detect.py").is_file(), "panel_detect.py must exist at repo root"


# --- FR-10: SKILL.md table removed, script invocation mandated ---


def test_skill_md_table_removed():
    text = CRITIQUE_SKILL.read_text()
    assert "| Files in scope | Panel | File |" not in text, (
        "skills/critique/SKILL.md must no longer carry the old prose trigger table"
    )


def test_skill_md_mandates_script_invocation():
    text = CRITIQUE_SKILL.read_text()
    assert "panel_detect.py" in text
    assert "context/panels/triggers.md" in text


def test_skill_md_mandates_per_candidate_disposition():
    text = CRITIQUE_SKILL.read_text().lower()
    assert "candidate" in text
    assert "disposition" in text or "activate or defer" in text


def test_skill_md_design_mode_uses_design_flag():
    text = CRITIQUE_SKILL.read_text()
    assert "--design" in text


def test_skill_md_surfaces_skipped_in_report_header():
    text = CRITIQUE_SKILL.read_text()
    assert "Skipped files:" in text, "report header must surface panel_detect.py's skipped list"


# --- FR-10: critic-brief.md repointed, stale "29 panels" prose gone ---


def test_critic_brief_repointed_and_stale_count_gone():
    text = CRITIC_BRIEF.read_text()
    assert "29 panels" not in text
    assert "panel_detect.py" in text
    assert "context/panels/triggers.md" in text


# --- FR-10: review SKILL.md repointed ---


def test_review_skill_repointed():
    text = REVIEW_SKILL.read_text()
    assert "panel_detect.py" in text
    assert "context/panels/triggers.md" in text


# --- FR-10: build-ticket.md flow repointed ---


def test_build_ticket_flow_repointed():
    text = BUILD_TICKET_FLOW.read_text()
    assert "panel_detect.py" in text
    assert "context/panels/triggers.md" in text


# --- FR-10: README.md repointed ---


def test_readme_repointed():
    text = README.read_text()
    assert "context/panels/triggers.md" in text
    assert "panel_detect.py" in text


# --- FR-10: all panel boilerplate lines cite triggers.md (AC: grep count = 0) ---


def test_no_panel_file_references_old_skill_md_table():
    offenders = [
        p.name for p in PANELS_DIR.glob("*.md")
        if "skills/critique/SKILL.md" in p.read_text()
    ]
    assert not offenders, f"panel files still reference the old table location: {offenders}"
