"""
Content-verification tests for context/flows/stack-advisor.md
Verifies the flow file documents all required behaviors per spec 0038-tech-stack-advisor-flow.
"""
from pathlib import Path

FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "stack-advisor.md"


def _section(content: str, start_header: str, end_header: str) -> str:
    start = content.find(start_header)
    end = content.find(end_header, start + len(start_header))
    assert start >= 0, f"Section '{start_header}' not found"
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
    guard = _section(content, "## Guard", "## new_artifact_detector")
    assert "## Tech Stack" in guard or "Tech Stack" in guard, \
        "Guard must document skip when ## Tech Stack already exists in requirements.md"


def test_guard_documents_no_stack_check_flag():
    content = FLOW_FILE.read_text()
    guard = _section(content, "## Guard", "## new_artifact_detector")
    assert "--no-stack-check" in guard, \
        "Guard must document the --no-stack-check flag as a skip condition"


# --- new_artifact_detector ---

def test_detector_requires_both_signals_for_high_confidence():
    content = FLOW_FILE.read_text()
    detector = _section(content, "## new_artifact_detector", "## stack_signal_collector")
    lower = detector.lower()
    assert "both" in lower, \
        "Detector must state BOTH signals are required for high confidence"


def test_detector_lists_keyword_signals():
    content = FLOW_FILE.read_text()
    detector = _section(content, "## new_artifact_detector", "## stack_signal_collector")
    for kw in ["new", "create", "build", "scaffold", "greenfield"]:
        assert kw in detector, f"Keyword signal '{kw}' must be listed in new_artifact_detector"


def test_detector_lists_all_manifest_filenames():
    content = FLOW_FILE.read_text()
    detector = _section(content, "## new_artifact_detector", "## stack_signal_collector")
    for manifest in ["pyproject.toml", "package.json", "Cargo.toml", "go.mod"]:
        assert manifest in detector, f"Manifest '{manifest}' must be listed in new_artifact_detector"


def test_detector_defaults_to_feature_addition_on_medium_low():
    content = FLOW_FILE.read_text()
    detector = _section(content, "## new_artifact_detector", "## stack_signal_collector")
    assert "feature-addition" in detector, \
        "Detector must document defaulting to feature-addition on medium/low confidence"


# --- stack_signal_collector ---

def test_signal_collector_reads_accepted_keys():
    content = FLOW_FILE.read_text()
    collector = _section(content, "## stack_signal_collector", "## proposal_builder")
    for key in ["language:", "framework:", "runtime:"]:
        assert key in collector, f"Key '{key}' must be documented in stack_signal_collector"


def test_signal_collector_rejects_aliases():
    content = FLOW_FILE.read_text()
    collector = _section(content, "## stack_signal_collector", "## proposal_builder")
    assert "tech_stack" in collector, \
        "Collector must mention tech_stack: as a rejected alias"


def test_signal_collector_existence_only_no_content_read():
    content = FLOW_FILE.read_text()
    collector = _section(content, "## stack_signal_collector", "## proposal_builder")
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
    collector = _section(content, "## stack_signal_collector", "## proposal_builder")
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


# --- proposal_builder ---

def test_proposal_builder_table_has_rationale_column():
    content = FLOW_FILE.read_text()
    builder = _section(content, "## proposal_builder", "## stack_approval_interaction")
    assert "Rationale" in builder, \
        "proposal_builder table must include a Rationale column"


def test_proposal_builder_table_has_source_column():
    content = FLOW_FILE.read_text()
    builder = _section(content, "## proposal_builder", "## stack_approval_interaction")
    assert "Source" in builder, \
        "proposal_builder table must include a Source column"


# --- stack_approval_interaction ---

def test_approval_interaction_max_2_rejection_termination():
    content = FLOW_FILE.read_text()
    approval = content[content.find("## stack_approval_interaction"):]
    lower = approval.lower()
    assert "2" in approval, "Approval interaction must document the 2-rejection limit"
    assert "reject" in lower, "Approval interaction must document rejection handling"


def test_approval_interaction_placeholder_comment_text():
    content = FLOW_FILE.read_text()
    approval = content[content.find("## stack_approval_interaction"):]
    assert "stack not specified" in approval, \
        "Approval interaction must include 'stack not specified' in the placeholder text"
    assert "fill in before /build" in approval, \
        "Approval interaction must include 'fill in before /build' in the placeholder text"


def test_approval_interaction_writes_tech_stack_to_requirements():
    content = FLOW_FILE.read_text()
    approval = content[content.find("## stack_approval_interaction"):]
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
