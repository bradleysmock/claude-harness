"""
Content-verification tests for ticket 0064 — critique report slimming.

Reads the three affected flow docs and asserts, via structural substrings,
that each now trims its session display of the critic's report to
header+verdict+finding-table (per spec 0064-critique-report-slimming-*).
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
BUILD_TICKET = ROOT / "context" / "flows" / "build-ticket.md"
BUILD_DRY_RUN = ROOT / "context" / "flows" / "build-dry-run-ticket.md"
AUTOPILOT_BATCH = ROOT / "context" / "flows" / "autopilot-batch.md"
REVIEW_SKILL = ROOT / "skills" / "review" / "SKILL.md"

SEVERITIES = ("BLOCKER", "MAJOR", "MINOR", "OBS")


def _section_from(content: str, start_header: str, end_header: str | None = None) -> str:
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


# --- File existence ---


def test_target_files_exist():
    assert BUILD_TICKET.exists()
    assert BUILD_DRY_RUN.exists()
    assert AUTOPILOT_BATCH.exists()
    assert REVIEW_SKILL.exists()


# --- FR-1: build-ticket.md trims display, keeps critic-findings.md append ---


def test_build_ticket_no_longer_instructs_verbatim_display():
    content = BUILD_TICKET.read_text()
    assert "Display the critic's structured report to the user verbatim." not in content
    assert "Display its report verbatim." not in content


def test_build_ticket_keeps_critic_findings_append_unchanged():
    content = BUILD_TICKET.read_text()
    assert "**Persist this round's report.**" in content
    assert "critic-findings.md" in content
    assert '`<commit-message>` = `chore(ticket): XXXX critic findings round 1`' in content


def test_build_ticket_trimmed_instruction_names_verdict_and_severities():
    step7 = _section_from(BUILD_TICKET.read_text(), "## Step 7 — Spawn post-build critic (automatic)", "### Step 7a")
    lower = step7.lower()
    assert "verdict" in lower
    for sev in SEVERITIES:
        assert sev in step7


# --- FR-2: build-dry-run-ticket.md writes + trims ---


def test_build_dry_run_writes_full_report_to_harness_critiques():
    content = BUILD_DRY_RUN.read_text()
    assert ".harness/critiques/" in content
    assert "critic_report_path" in content


def test_build_dry_run_step5_calls_render_with_path_and_trims():
    step5 = _section_from(BUILD_DRY_RUN.read_text(), "## Step 5")
    assert "render_dry_run_report(report, critic_report_path)" in step5
    lower = step5.lower()
    assert "verdict" in lower
    for sev in SEVERITIES:
        assert sev in step5
    assert "full report" in lower


# --- FR-3: autopilot-batch.md batch slug + per-member pointer + trim ---


def test_batch_writes_combined_report_with_batch_slug():
    step3 = _section_from(AUTOPILOT_BATCH.read_text(), "## Step 3")
    assert "batch-<lead-slug>-<YYYY-MM-DD>" in step3
    assert ".harness/critiques/" in step3


def test_batch_appends_pointer_to_every_member_critic_findings():
    step3 = _section_from(AUTOPILOT_BATCH.read_text(), "## Step 3")
    assert "## Critique pointers" in step3
    assert "critic-findings.md" in step3


def test_batch_trimmed_instruction_names_verdict_and_severities():
    step3 = _section_from(AUTOPILOT_BATCH.read_text(), "## Step 3", "## Step 4")
    lower = step3.lower()
    assert "verdict" in lower
    for sev in SEVERITIES:
        assert sev in step3


# --- FR-5: review skill untouched (regression guard) ---


def test_review_skill_step6_remains_file_less_and_interactive():
    content = REVIEW_SKILL.read_text()
    assert "do **not** write the report to" in content
    assert "the interactive conversation is the deliverable" in content
    assert ".harness/critiques" not in content
