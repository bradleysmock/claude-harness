"""
Content-verification tests for the requirements-review skill (ticket 0034).

Verifies that skills/requirements-review/SKILL.md documents every required
behavior from requirements.md, that the thin command invoker exists, and that the
five regression fixtures exhibit their seeded defects. The dimension-detection
behavior itself is LLM-driven and evaluated manually (see the skill README); these
tests guard the structural contract that keeps the skill trustworthy.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKILL = ROOT / "skills" / "requirements-review" / "SKILL.md"
COMMAND = ROOT / "commands" / "requirements-review.md"
FIXTURES = ROOT / "skills" / "requirements-review" / "fixtures"
ANALYST_AGENT = ROOT / "agents" / "requirements-analyst.md"


def _skill() -> str:
    return SKILL.read_text()


# --- skill file + frontmatter ------------------------------------------------

def test_skill_file_exists():
    assert SKILL.exists(), "skills/requirements-review/SKILL.md must exist"


def test_skill_has_frontmatter_name_and_description():
    content = _skill()
    assert content.startswith("---"), "SKILL.md must open with YAML frontmatter"
    front = content.split("---", 2)[1]
    assert "name: requirements-review" in front, "frontmatter must set name: requirements-review"
    assert "description:" in front, "frontmatter must include a description"


def test_description_has_trigger_and_skip():
    front = _skill().split("---", 2)[1]
    assert "TRIGGER" in front and "SKIP" in front, "description must document TRIGGER and SKIP"


# --- FR-8 / path containment -------------------------------------------------

def test_documents_four_digit_number_resolution():
    content = _skill()
    assert "four-digit" in content.lower() or "[0-9]{4}" in content, \
        "skill must resolve the four-digit ticket number to a slug (FR-8)"


def test_documents_path_containment():
    content = _skill().lower()
    assert "containment" in content, "skill must document path containment (traversal defense)"
    assert ".." in _skill(), "skill must call out `..` / traversal as a rejected input"
    assert "direct child" in content, "resolved dir must be validated as a direct child of .tickets/"


def test_documents_ambiguous_and_missing_ticket_halts():
    content = _skill().lower()
    assert "ambiguous" in content, "skill must halt on an ambiguous ticket-number match"
    assert "no ticket found" in content or "zero" in content, \
        "skill must halt when no ticket matches"


# --- FR-9 / guard ------------------------------------------------------------

def test_guard_missing_artifact_no_partial_file():
    content = _skill()
    lower = content.lower()
    assert "problem.md" in content and "requirements.md" in content
    assert "halt" in lower or "stop" in lower, "missing artifact must halt (FR-9)"
    assert "partial" in lower, "skill must state no partial findings file is written on guard failure (FR-9)"


# --- NFR-4 / read-only subagent ---------------------------------------------

def test_analysis_subagent_is_read_only():
    content = _skill()
    assert "Read, Grep, Glob" in content or "Read/Grep/Glob" in content, \
        "analysis subagent must be restricted to Read, Grep, Glob (NFR-4)"
    assert "no file-write" in content.lower(), \
        "skill must state the analysis context has no file-write tools (NFR-4)"


def test_dispatches_dedicated_readonly_agent_not_general_purpose():
    """B-1: tool restriction must be architectural (agent definition), not prose."""
    content = _skill()
    assert "requirements-analyst" in content, \
        "skill must dispatch the dedicated requirements-analyst agent (NFR-4 enforced structurally)"
    assert "general-purpose" not in content, \
        "skill must NOT use general-purpose (its tools cannot be narrowed by prose) — B-1"


def test_analyst_agent_definition_is_read_only():
    """B-1: the agent definition's frontmatter enforces the read-only tool set."""
    assert ANALYST_AGENT.exists(), "agents/requirements-analyst.md must exist"
    front = ANALYST_AGENT.read_text().split("---", 2)[1]
    assert "name: requirements-analyst" in front
    assert "tools: Read, Grep, Glob" in front, \
        "agent frontmatter must restrict tools to Read, Grep, Glob (NFR-4)"


def test_parent_does_not_read_untrusted_bodies():
    """M-1: the write-capable parent must not ingest untrusted artifact bodies."""
    content = _skill().lower()
    assert "do not read the artifact bodies" in content or "not read the untrusted" in content, \
        "parent must not read the untrusted problem.md/requirements.md bodies (M-1)"
    assert "paths" in content, "parent must pass file paths to the subagent (M-1)"


def test_title_sourced_from_subagent_return():
    """M-1: the report title comes from the subagent's validated return, not a parent read."""
    content = _skill()
    assert "TITLE:" in content, "subagent return must include a TITLE line (M-1)"


def test_trust_boundary_documented():
    content = _skill().lower()
    assert "untrusted" in content, "skill must mark ticket content as untrusted"
    assert "ignore previous instructions" in content, \
        "skill must document the injection trust boundary explicitly"


# --- FR-3 / four dimensions --------------------------------------------------

def test_all_four_dimensions_named():
    content = _skill()
    for dim in ("Completeness", "Testability", "Coverage", "Consistency"):
        assert f"**{dim}**" in content, f"dimension '{dim}' must be named (FR-3)"


def test_completeness_and_coverage_are_distinguished():
    content = _skill()
    lower = content.lower()
    assert "distinct from coverage" in lower or "distinct from completeness" in lower, \
        "Completeness and Coverage must be explicitly differentiated (FR-3)"


def test_testability_requires_measurable_threshold():
    content = _skill().lower()
    assert "measurable threshold" in content, "Testability must require a measurable threshold (FR-3)"
    assert "concrete reason" in content, \
        "Testability must require a concrete reason, not subjective wording (risk mitigation)"


def test_consistency_compares_all_fr_pairs():
    content = _skill().lower()
    assert "each fr pair" in content, "Consistency must compare each FR pair, not only adjacent (FR-3)"
    assert "both fr numbers" in content or "references both" in content, \
        "a Consistency finding must reference both FR numbers (FR-3)"


# --- FR-4 / FR-5 / output ----------------------------------------------------

def test_output_file_and_distinct_from_gate_findings():
    content = _skill()
    assert "requirements-findings.md" in content, "output must go to requirements-findings.md (FR-4)"
    assert "gate-findings.md" in content, "report must be called out as distinct from gate-findings.md"


def test_each_finding_has_dimension_description_fix():
    content = _skill()
    assert "DIMENSION" in content and "DESCRIPTION" in content and "FIX" in content, \
        "each finding must include dimension, description, and fix (FR-5)"


def test_parent_validates_subagent_return():
    content = _skill().lower()
    assert "malformed" in content, "parent must halt on a malformed subagent return"


def test_observability_echo_before_write():
    content = _skill().lower()
    assert "echo" in content and "observability" in content, \
        "skill must echo findings to the operator before writing (observability rule)"


# --- FR-6 / clean report -----------------------------------------------------

def test_no_findings_exact_phrase():
    content = _skill()
    assert "No findings — requirements are complete, testable, covered, and consistent." in content, \
        "clean report must use the exact FR-6 phrase"


# --- FR-7 / NFR-2 / NFR-3 ----------------------------------------------------

def test_read_only_wrt_artifacts():
    content = _skill().lower()
    assert "read-only" in content, "skill must be read-only wrt problem.md/requirements.md (FR-7/NFR-3)"
    assert "does not modify" in content or "not modify" in content, \
        "skill must state it does not modify problem.md / requirements.md (FR-7)"


def test_per_finding_line_cap_and_no_count_cap():
    content = _skill()
    assert "5 lines" in content, "each finding must be capped at 5 lines (NFR-2)"
    assert "no cap on the number" in content.lower(), "there must be no cap on the number of findings (NFR-2)"


def test_does_not_read_solution_md():
    content = _skill().lower()
    assert "does not read `solution.md`" in content or "not read solution.md" in content, \
        "skill must state it does not read solution.md (out of scope)"


# --- command invoker ---------------------------------------------------------

def test_command_invoker_exists_and_references_skill():
    assert COMMAND.exists(), "commands/requirements-review.md must exist for /requirements-review"
    text = COMMAND.read_text()
    assert "requirements-review" in text and "Skill tool" in text, \
        "command must invoke the requirements-review skill via the Skill tool"


# --- fixtures ----------------------------------------------------------------

FIXTURE_NAMES = [
    "completeness-defect",
    "testability-defect",
    "coverage-defect",
    "consistency-defect",
    "clean",
]


def test_all_fixtures_exist_with_both_artifacts():
    for name in FIXTURE_NAMES:
        d = FIXTURES / name
        assert (d / "problem.md").exists(), f"{name}/problem.md must exist"
        assert (d / "requirements.md").exists(), f"{name}/requirements.md must exist"


def test_testability_fixture_has_untestable_ac():
    text = (FIXTURES / "testability-defect" / "requirements.md").read_text().lower()
    assert "should feel responsive" in text, "testability fixture must seed an untestable AC"


def test_consistency_fixture_has_contradiction():
    text = (FIXTURES / "consistency-defect" / "requirements.md").read_text().lower()
    assert "must retry" in text and "must never retry" in text, \
        "consistency fixture must seed an FR contradiction"


def test_coverage_fixture_criterion_absent_from_acs():
    req = (FIXTURES / "coverage-defect" / "requirements.md").read_text().lower()
    prob = (FIXTURES / "coverage-defect" / "problem.md").read_text().lower()
    assert "no-findings summary" in prob, "coverage fixture problem.md must state the criterion"
    assert "no-findings summary" not in req, \
        "coverage fixture requirements.md must omit the criterion (the seeded gap)"


def test_clean_fixture_has_no_contradiction():
    text = (FIXTURES / "clean" / "requirements.md").read_text().lower()
    assert "must never" not in text, "clean fixture must not contain a contradiction"
