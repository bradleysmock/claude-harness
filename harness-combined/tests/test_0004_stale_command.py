"""Content-verification tests for skills/stale/SKILL.md (ticket 0004).

This ticket adds a model-interpreted Markdown skill, not Python code. These tests
verify the SKILL.md documents every behavior required by spec
0004-stale-ticket-detector-command: frontmatter, the untrusted-data trust
boundary, strict date parsing, threshold precedence, the strict-greater-than
staleness test, graceful skip/degraded-confidence handling, the currentDate
guard, and the required per-ticket display fields.

Limitation: these tests verify the instructions exist, not that the model
executes them at runtime.
"""
from pathlib import Path

SKILL = Path(__file__).parent.parent / "skills" / "stale" / "SKILL.md"


def _content() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert SKILL.exists(), "skills/stale/SKILL.md must exist"


def test_frontmatter_names_stale():
    content = _content()
    assert content.startswith("---"), "SKILL.md must open with YAML frontmatter"
    head = content.split("---", 2)[1]
    assert "name: stale" in head, "frontmatter must declare name: stale"
    assert "description:" in head, "frontmatter must include a description"


def test_scan_excludes_completed_via_depth():
    content = _content()
    assert ".tickets/*/status.md" in content, "must scan .tickets/*/status.md"
    lower = content.lower()
    assert "one level deep" in lower, "must document one-level-deep scan"
    assert "completed" in lower, "must document excluding completed/ tickets"


def test_structural_prefix_extraction_of_three_fields_only():
    content = _content()
    for field in ["title:", "status:", "updated:"]:
        assert field in content, f"must document extracting the {field} field"
    lower = content.lower()
    assert "prefix" in lower, "must document structural prefix matching"
    assert "trust boundary" in lower, "must state the trust boundary on file reads"


def test_untrusted_data_block_scoping():
    content = _content()
    assert "[STALE TICKET DATA - UNTRUSTED]" in content, \
        "must scope extracted values in a [STALE TICKET DATA - UNTRUSTED] block"
    lower = content.lower()
    assert "data only" in lower, "block must state values are data only"
    assert "instruction" in lower or "command" in lower, \
        "block must state values must not be interpreted as instructions/commands"


def test_json_array_encoding_with_required_keys():
    content = _content()
    for key in ['"number"', '"title"', '"status"', '"days_idle"']:
        assert key in content, f"JSON data block must carry the {key} key"


def test_table_built_from_scoped_block_not_raw_reads():
    content = _content()
    lower = content.lower()
    assert "already-scoped" in lower or "from this already-scoped" in lower, \
        "table must be generated from the scoped JSON block, not raw file reads"


def test_calendar_days_semantics_documented():
    content = _content()
    lower = content.lower()
    assert "calendar days" in lower, "days_idle must be documented as calendar days"
    assert "floor" in lower, "days_idle must be floor(currentDate - updated_date)"


def test_strict_greater_than_threshold_boundary():
    content = _content()
    lower = content.lower()
    assert "strictly greater than" in lower, "staleness test must be strictly greater than"
    # Boundary examples: exactly 7 is NOT stale, 8 IS stale.
    assert "exactly 7" in lower, "must document that idle exactly 7 days is NOT stale"
    assert "8 days" in lower, "must document that idle 8 days IS stale"


def test_threshold_precedence_flag_over_standards_over_default():
    content = _content()
    # Scope to the threshold-resolution section so the frontmatter's "default 7 days"
    # description phrase does not confuse ordering.
    start = content.find("## Step 1 — Resolve the threshold")
    end = content.find("## Step 2")
    assert start >= 0 and end > start, "must have a Step 1 threshold-resolution section"
    section = content[start:end]
    flag = section.find("--days")
    standards = section.find("stale_threshold_days")
    default = section.find("Default: 7")
    assert flag >= 0 and standards >= 0 and default >= 0, \
        "Step 1 must document --days, stale_threshold_days, and a Default: 7"
    assert flag < standards < default, \
        "precedence order must be --days > stale_threshold_days > default"


def test_standards_value_validated_positive_int_max_365():
    content = _content()
    assert "365" in content, "stale_threshold_days must be validated as <= 365"
    lower = content.lower()
    assert "positive integer" in lower, "stale_threshold_days must be a positive integer"
    assert "using default 7" in content or "default of 7" in content or "default 7" in content, \
        "invalid stale_threshold_days must fall back to default 7 with a warning"


def test_days_flag_validation_error_not_silent():
    content = _content()
    assert "--days abc" in content, "must document the --days abc invalid-input case"
    lower = content.lower()
    assert "validation error" in lower or "error:" in lower, \
        "invalid --days must emit a validation error, not a silent skip"


def test_standards_trust_boundary_discards_rest():
    content = _content()
    lower = content.lower()
    assert "discard" in lower and "_standards.md" in content, \
        "must discard the rest of _standards.md (only stale_threshold_days enters context)"


def test_strict_iso_date_parsing_skips_malformed():
    content = _content()
    assert "2026-6-1" in content, "must treat non-zero-padded dates as malformed"
    assert "06/21/2026" in content, "must treat non-ISO dates as malformed"
    lower = content.lower()
    assert "malformed" in lower, "must document malformed-date skipping"
    assert "skip, not a guess" in lower, "ambiguous dates must be a skip, not a guess"


def test_skip_count_and_degraded_confidence_warning():
    content = _content()
    lower = content.lower()
    assert "skipped" in lower, "must append a skip count when skips occur"
    assert "25%" in content, "must emit a degraded-confidence warning above 25% skipped"


def test_currentdate_unavailable_guard():
    content = _content()
    assert "currentDate unavailable" in content, \
        "must emit an explicit warning when currentDate is unavailable"
    lower = content.lower()
    assert "no" in lower and "staleness" in lower, \
        "must produce no staleness output when currentDate is unavailable"


def test_empty_result_outputs_no_stale_tickets():
    content = _content()
    assert "No stale tickets" in content, \
        "must output 'No stale tickets' on the empty/fresh/absent cases (not silence)"


def test_reports_required_display_fields():
    content = _content()
    # Per-ticket display: number, title, status, days idle.
    assert "Ticket" in content and "Title" in content and "Status" in content, \
        "report table must show ticket number, title, and status"
    assert "Days idle" in content or "days_idle" in content, \
        "report must show integer days idle per ticket"
