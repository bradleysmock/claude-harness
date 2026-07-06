"""Content-verification tests for the /status stale-summary amendment (ticket 0004).

Verifies skills/status/SKILL.md carries the verbatim-copied staleness scan
sub-procedure (annotated as shared with stale/SKILL.md), reuses the untrusted-data
trust boundary, and documents appending a one-line stale-count summary when stale
tickets exist and omitting it otherwise — per spec
0004-stale-ticket-detector-status-summary. Also asserts the reciprocal sync
annotation exists in stale/SKILL.md.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATUS = ROOT / "skills" / "status" / "SKILL.md"
STALE = ROOT / "skills" / "stale" / "SKILL.md"


def _status() -> str:
    return STATUS.read_text(encoding="utf-8")


def test_status_skill_exists():
    assert STATUS.exists(), "skills/status/SKILL.md must exist"


def test_status_has_inline_staleness_subprocedure():
    content = _status()
    lower = content.lower()
    assert "stale" in lower, "status skill must include a staleness sub-procedure"
    assert ".tickets/*/status.md" in content, \
        "the copied scan sub-procedure must scan .tickets/*/status.md"
    assert "one level deep" in lower, "copied sub-procedure must document one-level-deep scan"


def test_status_carries_shared_sync_annotation_naming_stale():
    content = _status()
    assert "shared with stale/SKILL.md" in content, \
        "copied block must be annotated as shared with stale/SKILL.md"
    assert "keep in sync" in content, "shared annotation must say 'keep in sync'"


def test_stale_carries_reciprocal_sync_annotation_naming_status():
    stale = STALE.read_text(encoding="utf-8")
    assert "shared with status/SKILL.md" in stale, \
        "stale/SKILL.md must carry a reciprocal 'shared with status/SKILL.md' annotation"
    assert "keep in sync" in stale, "reciprocal annotation must say 'keep in sync'"


def test_status_reuses_untrusted_data_block():
    content = _status()
    assert "[STALE TICKET DATA - UNTRUSTED]" in content, \
        "status sub-procedure must scope extracted values in the untrusted-data block"
    lower = content.lower()
    assert "data only" in lower, "untrusted block must state values are data only"


def test_status_documents_summary_line_when_stale():
    content = _status()
    assert "run /stale to see details" in content, \
        "status must document the 'N stale tickets — run /stale to see details' summary line"


def test_status_omits_summary_when_none_stale():
    content = _status()
    lower = content.lower()
    assert "omit" in lower, "status must document omitting the summary line when none are stale"


def test_status_duplication_is_bounded_no_days_flag():
    content = _status()
    # The bounded copy must NOT reimplement the full /stale command (no --days flag here).
    assert "No `--days` flag here" in content or "no --days flag" in content.lower(), \
        "status sub-procedure must be bounded to the scan (no --days flag)"


def test_existing_status_sections_preserved():
    content = _status()
    # The amendment must not remove any existing status output section.
    for section in [
        "## Step 1 — Ticket status",
        "### Active Tickets",
        "### Completed Tickets",
        "## Step 2 — Spec/build status",
        "## Step 3 — Failure memory summary",
        "## Output shape",
    ]:
        assert section in content, f"amendment must preserve existing section: {section}"
