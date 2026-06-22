"""
Content-verification tests for context/flows/stack-advisor.md
Verifies the flow file documents all required behaviors per spec 0038-tech-stack-advisor-flow.
"""
from pathlib import Path

FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "stack-advisor.md"


def _section_from(content: str, start_header: str, end_header: str | None = None) -> str:
    """Extract a section from start_header to end_header (or end of file if end_header is None)."""
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


def test_flow_file_exists():
    assert FLOW_FILE.exists(), "context/flows/stack-advisor.md must exist"


def test_guard_section_is_first_section():
    content = FLOW_FILE.read_text()
    guard_pos = content.find("## Guard")
    detector_pos = content.find("## new_artifact_detector")
    assert guard_pos > 0, "## Guard section must exist"
    assert guard_pos < detector_pos, "Guard must appear before new_artifact_detector"


def test_guard_documents_existing_tech_stack_skip():
    content = FLOW_FILE.read_text()
    guard = _section_from(content, "## Guard", "## new_artifact_detector")
    assert "## Tech Stack" in guard or "Tech Stack" in guard, \
        "Guard must document skip when ## Tech Stack already exists in requirements.md"


def test_guard_documents_no_stack_check_flag():
    content = FLOW_FILE.read_text()
    guard = _section_from(content, "## Guard", "## new_artifact_detector")
    assert "--no-stack-check" in guard, \
        "Guard must document the --no-stack-check flag as a skip condition"


def test_guard_distinguishes_placeholder_from_populated_stack():
    content = FLOW_FILE.read_text()
    guard = _section_from(content, "## Guard", "## new_artifact_detector")
    # Guard must clarify that placeholder-only sections do NOT trigger the skip
    assert "placeholder" in guard.lower(), \
        "Guard must clarify that a placeholder-only ## Tech Stack section does not trigger the skip"


# --- new_artifact_detector ---

def test_detector_requires_both_signals_for_high_confidence():
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    lower = detector.lower()
    assert "both" in lower, \
        "Detector must state BOTH signals are required for high confidence"


def test_detector_lists_keyword_signals():
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    for kw in ["new", "create", "build", "scaffold", "greenfield"]:
        assert kw in detector, f"Keyword signal '{kw}' must be listed in new_artifact_detector"


def test_detector_lists_all_manifest_filenames():
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    for manifest in ["pyproject.toml", "package.json", "Cargo.toml", "go.mod"]:
        assert manifest in detector, f"Manifest '{manifest}' must be listed in new_artifact_detector"


def test_detector_defaults_to_feature_addition_on_medium_low():
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    assert "feature-addition" in detector, \
        "Detector must document defaulting to feature-addition on medium/low confidence"


# B-01: 8-case classification coverage (FR-1, NFR-2)

def test_detector_has_reference_classification_table():
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    assert "Reference classification cases" in detector or "classification cases" in detector.lower(), \
        "Detector must include reference classification cases (≥8 required by NFR-2)"


def test_detector_classification_cases_cover_high_confidence_new_app():
    """Case 1: new app with no manifest → high/trigger"""
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    assert "high/trigger" in detector or ("high" in detector and "trigger" in detector), \
        "Detector must document high-confidence trigger case for new app with no manifest"


def test_detector_classification_cases_cover_feature_with_manifest():
    """Case 2: feature + manifest → feature-addition (keyword present but manifest found)"""
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    # Verify keyword-present + manifest-found → medium → feature-addition
    assert "manifest found" in detector.lower() or "manifest present" in detector.lower(), \
        "Detector must document that keyword + manifest-present yields feature-addition"


def test_detector_classification_cases_cover_no_keyword():
    """Cases 4, 5, 6: no keyword → low confidence → feature-addition regardless of manifest"""
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    # The classification table must show Absent keyword → low → feature-addition
    assert "Absent" in detector or "absent" in detector.lower(), \
        "Detector must document that absent keyword yields feature-addition (low confidence)"


def test_detector_has_at_least_8_classification_cases():
    """NFR-2: at least 8 cases must be enumerated in the reference table"""
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    # Count table rows that look like case entries (numbered 1. through 8.)
    case_count = sum(1 for line in detector.splitlines() if line.strip().startswith("| ") and
                     any(f"{n}." in line for n in range(1, 9)))
    assert case_count >= 8, \
        f"Detector must enumerate ≥8 classification cases in a reference table, found {case_count}"


def test_detector_keyword_plus_manifest_yields_feature_addition_not_trigger():
    """Case 3: 'new' keyword present but manifest found → feature-addition (not triggered)"""
    content = FLOW_FILE.read_text()
    detector = _section_from(content, "## new_artifact_detector", "## stack_signal_collector")
    # The classification table must show medium row → feature-addition when manifest is present
    assert "medium" in detector.lower() and "feature-addition" in detector, \
        "Detector must document medium-confidence → feature-addition when manifest is found"


# --- stack_signal_collector ---

def test_signal_collector_reads_accepted_keys():
    content = FLOW_FILE.read_text()
    collector = _section_from(content, "## stack_signal_collector", "## proposal_builder")
    for key in ["language:", "framework:", "runtime:"]:
        assert key in collector, f"Key '{key}' must be documented in stack_signal_collector"


def test_signal_collector_rejects_aliases():
    content = FLOW_FILE.read_text()
    collector = _section_from(content, "## stack_signal_collector", "## proposal_builder")
    assert "tech_stack" in collector, \
        "Collector must mention tech_stack: as a rejected alias"


def test_signal_collector_existence_only_no_content_read():
    content = FLOW_FILE.read_text()
    collector = _section_from(content, "## stack_signal_collector", "## proposal_builder")
    lower = collector.lower()
    has_existence_only = (
        "existence" in lower or
        "not read" in lower or
        "do not" in lower or
        "no content" in lower
    )
    assert has_existence_only, \
        "Collector must state manifest file content is not read (existence check only)"


def test_signal_collector_documents_priority_order():
    content = FLOW_FILE.read_text()
    collector = _section_from(content, "## stack_signal_collector", "## proposal_builder")
    standards_pos = collector.find("_standards.md")
    manifest_pos = collector.find("manifest", standards_pos)
    request_pos = collector.find("request", manifest_pos)
    default_pos = collector.find("default", request_pos)
    assert standards_pos >= 0 and manifest_pos > standards_pos, \
        "_standards.md must appear before manifest in priority order"
    assert manifest_pos >= 0 and request_pos > manifest_pos, \
        "manifest must appear before request in priority order"
    assert request_pos >= 0 and default_pos > request_pos, \
        "request must appear before default in priority order"


def test_signal_collector_documents_value_validation():
    """B-03: extracted values must be bounded to prevent injection-shaped content"""
    content = FLOW_FILE.read_text()
    collector = _section_from(content, "## stack_signal_collector", "## proposal_builder")
    lower = collector.lower()
    has_length_bound = "64" in collector or "length" in lower or "≤" in collector
    has_validation = "validation" in lower or "dropped" in lower or "silently" in lower
    assert has_length_bound, \
        "Collector must document a length bound (≤ 64 chars) on extracted values (B-03)"
    assert has_validation, \
        "Collector must state that values failing validation are silently dropped (B-03)"


def test_signal_collector_value_validation_prohibits_newlines():
    """B-03: multi-line / newline values must be rejected"""
    content = FLOW_FILE.read_text()
    collector = _section_from(content, "## stack_signal_collector", "## proposal_builder")
    lower = collector.lower()
    assert "newline" in lower or "single line" in lower or "no newline" in lower, \
        "Collector must state that multi-line values (with newlines) are rejected (B-03)"


# --- proposal_builder ---

def test_proposal_builder_table_has_rationale_column():
    content = FLOW_FILE.read_text()
    builder = _section_from(content, "## proposal_builder", "## stack_approval_interaction")
    assert "Rationale" in builder, \
        "proposal_builder table must include a Rationale column"


def test_proposal_builder_table_has_source_column():
    content = FLOW_FILE.read_text()
    builder = _section_from(content, "## proposal_builder", "## stack_approval_interaction")
    assert "Source" in builder, \
        "proposal_builder table must include a Source column"


# --- stack_approval_interaction ---

def test_approval_interaction_max_2_rejection_termination():
    content = FLOW_FILE.read_text()
    approval = _section_from(content, "## stack_approval_interaction")
    lower = approval.lower()
    assert "2" in approval, "Approval interaction must document the 2-rejection limit"
    assert "reject" in lower, "Approval interaction must document rejection handling"


def test_approval_interaction_handles_invalid_empty_response():
    """B-02: invalid/empty responses must also increment rejection_count"""
    content = FLOW_FILE.read_text()
    approval = _section_from(content, "## stack_approval_interaction")
    lower = approval.lower()
    assert "invalid" in lower or "empty" in lower, \
        "Approval interaction must document that invalid/empty responses increment the rejection counter (B-02)"


def test_approval_interaction_mixed_rejection_and_invalid_terminates():
    """B-02: 'one of each' (rejection + invalid) must trigger exhaustion"""
    content = FLOW_FILE.read_text()
    approval = _section_from(content, "## stack_approval_interaction")
    lower = approval.lower()
    # Both 'reject' and 'invalid'/'empty' must be covered as exhaustion triggers
    has_reject = "reject" in lower
    has_invalid_or_empty = "invalid" in lower or "empty" in lower
    assert has_reject and has_invalid_or_empty, \
        "Approval interaction must document that rejection AND invalid responses both count toward exhaustion (FR-7)"


def test_approval_interaction_placeholder_comment_text():
    content = FLOW_FILE.read_text()
    approval = _section_from(content, "## stack_approval_interaction")
    assert "stack not specified" in approval, \
        "Approval interaction must include 'stack not specified' in the placeholder text"
    assert "fill in before /build" in approval, \
        "Approval interaction must include 'fill in before /build' in the placeholder text"


def test_approval_interaction_writes_tech_stack_to_requirements():
    content = FLOW_FILE.read_text()
    approval = _section_from(content, "## stack_approval_interaction")
    assert "requirements.md" in approval, \
        "Approval interaction must document writing to requirements.md"
    assert "## Tech Stack" in approval, \
        "Approval interaction must document writing to the ## Tech Stack section"


def test_all_five_sections_present():
    content = FLOW_FILE.read_text()
    for section in [
        "## Guard",
        "## new_artifact_detector",
        "## stack_signal_collector",
        "## proposal_builder",
        "## stack_approval_interaction",
    ]:
        assert section in content, f"Section '{section}' must be present in stack-advisor.md"
