"""
Structural doc-tests for the craft polish pass (gate-locked, behaviour-preserving).

Mirrors the test_0049 pattern: reads the affected markdown files and asserts, via
structural substrings, that the new craft subagent, the build-ticket Step 7b.5
polish loop, the config declaration, and the report/gitignore wiring are all
documented per docs/superpowers/specs/2026-07-19-craft-polish-pass-design.md.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
CRAFT_AGENT = ROOT / "agents" / "craft.md"
BUILD_TICKET = ROOT / "context" / "flows" / "build-ticket.md"
INIT_CMD = ROOT / "commands" / "init.md"
HARNESS_REF = ROOT / "context" / "harness-reference.md"
README = ROOT / "README.md"
GITIGNORE = ROOT / ".gitignore"

TAXONOMY = ("rename", "extract", "inline", "comment", "delete", "simplify", "error_handling")
TERMINAL_STATUSES = ("converged", "max_iterations_reached", "disabled")


def _section_from(content: str, start_header: str, end_header: str | None = None) -> str:
    """Extract a section from start_header to end_header (or end of file)."""
    start = content.find(start_header)
    assert start >= 0, f"Section '{start_header}' not found"
    if end_header is None:
        return content[start:]
    end = content.find(end_header, start + len(start_header))
    return content[start:end] if end >= 0 else content[start:]


def _normalize(text: str) -> str:
    """Strip markdown emphasis/backticks and collapse whitespace, lowercased."""
    for ch in ("`", "*", "—"):
        text = text.replace(ch, " ")
    return " ".join(text.lower().split())


# --- File existence ---

def test_craft_agent_exists():
    assert CRAFT_AGENT.exists(), "agents/craft.md must exist"


def test_target_docs_exist():
    assert BUILD_TICKET.exists(), "context/flows/build-ticket.md must exist"
    assert INIT_CMD.exists(), "commands/init.md must exist"
    assert HARNESS_REF.exists(), "context/harness-reference.md must exist"
    assert README.exists(), "README.md must exist"
    assert GITIGNORE.exists(), ".gitignore must exist"


# --- agents/craft.md — taxonomy, exact phrase, JSON order, asymmetric exposure ---

def test_craft_agent_lists_seven_taxonomy_categories():
    content = CRAFT_AGENT.read_text()
    for cat in TAXONOMY:
        assert cat in content, f"craft.md must name the '{cat}' taxonomy category"


def test_craft_agent_contains_exact_behaviour_phrase():
    """The exact spelling 'behaviour must not change' (British 'behaviour') is required."""
    content = CRAFT_AGENT.read_text()
    assert "behaviour must not change" in content, \
        "craft.md must contain the exact phrase 'behaviour must not change'"


def test_craft_agent_documents_fixed_json_field_order():
    content = CRAFT_AGENT.read_text()
    fields = ("reasoning", "improvements", "polished_implementation", "polished_tests")
    positions = [content.find(f) for f in fields]
    for f, pos in zip(fields, positions):
        assert pos >= 0, f"craft.md must document the '{f}' JSON field"
    assert positions == sorted(positions), \
        "craft.md must present the JSON fields in the fixed order: " \
        "reasoning, improvements, polished_implementation, polished_tests"


def test_craft_agent_documents_improvement_shape():
    content = CRAFT_AGENT.read_text()
    for field in ("category", "location_hint", "rationale"):
        assert field in content, f"each improvement must carry the '{field}' field"


def test_craft_agent_uses_asymmetric_exposure():
    """The craft prompt must not leak implementer reasoning framing (critic pattern)."""
    lower = CRAFT_AGENT.read_text().lower()
    for banned in ("confident_about", "uncertain_about", "falsification"):
        assert banned not in lower, \
            f"craft.md must not expose implementer reasoning field '{banned}'"
    assert "entire deliverable" in lower, \
        "craft.md must state its response is the entire deliverable (asymmetric exposure)"


def test_craft_agent_cites_specific_identifier_or_line():
    lower = CRAFT_AGENT.read_text().lower()
    assert "identifier" in lower or "line" in lower, \
        "craft.md must require each improvement to cite a specific identifier or line"


# --- build-ticket.md Step 7b.5 — gate re-run, pinned-test-survival, commits, statuses ---

def _step_7b5() -> str:
    return _section_from(BUILD_TICKET.read_text(), "Step 7b.5", "## Step 8") \
        if "## Step 8" in BUILD_TICKET.read_text() else \
        _section_from(BUILD_TICKET.read_text(), "Step 7b.5")


def test_build_ticket_has_step_7b5():
    assert "7b.5" in BUILD_TICKET.read_text(), \
        "build-ticket.md must introduce Step 7b.5 (craft polish loop)"


def test_step_7b5_reruns_the_gate():
    step = _step_7b5()
    assert "gate_run_on_dir" in step, \
        "Step 7b.5 must re-run gate_run_on_dir against the polished worktree"


def test_step_7b5_documents_pinned_test_survival():
    norm = _normalize(_step_7b5())
    assert "pinned" in norm and "survival" in norm, \
        "Step 7b.5 must document the pinned-test-survival guard"
    assert "pre-polish" in norm or "pre polish" in norm, \
        "Step 7b.5 must pin the pre-polish test files as the anti-cheat reference"


def test_step_7b5_reverts_on_break():
    norm = _normalize(_step_7b5())
    assert "revert" in norm, \
        "Step 7b.5 must revert a round on any new gate failure or pinned-test failure"


def test_step_7b5_commits_each_accepted_round():
    step = _step_7b5()
    assert "commit" in step.lower(), \
        "Step 7b.5 must commit each accepted polish round as its own commit"


def test_step_7b5_documents_three_terminal_statuses():
    step = _step_7b5()
    for status in TERMINAL_STATUSES:
        assert status in step, \
            f"Step 7b.5 must document the '{status}' terminal status"


def test_step_7b5_documents_disabled_path():
    norm = _normalize(_step_7b5())
    assert "craft_max_iterations == 0" in norm or "craft_max_iterations==0" in norm, \
        "Step 7b.5 must document the CRAFT_MAX_ITERATIONS == 0 disabled path"


def test_step_7b5_names_the_craft_subagent():
    norm = _normalize(_step_7b5())
    assert "craft" in norm and "subagent" in norm, \
        "Step 7b.5 must spawn the craft subagent"


# --- Config: CRAFT_MAX_ITERATIONS declared like MAX_REPAIR_ATTEMPTS ---

def test_config_declares_craft_max_iterations():
    """CRAFT_MAX_ITERATIONS must be declared in init's config.py block, like MAX_REPAIR_ATTEMPTS."""
    content = INIT_CMD.read_text()
    config = _section_from(content, "### 2", "### 3")
    assert "MAX_REPAIR_ATTEMPTS" in config, "sanity: config block should still declare MAX_REPAIR_ATTEMPTS"
    assert "CRAFT_MAX_ITERATIONS" in config, \
        "init.md config.py block must declare CRAFT_MAX_ITERATIONS"
    assert "= 3" in config, "CRAFT_MAX_ITERATIONS default must be 3"


def test_config_documents_zero_disables():
    config = _section_from(INIT_CMD.read_text(), "### 2", "### 3")
    norm = _normalize(config)
    assert "disable" in norm, "config must note that 0 disables the craft polish pass"


def test_config_declares_require_test_survival():
    config = _section_from(INIT_CMD.read_text(), "### 2", "### 3")
    assert "CRAFT_REQUIRE_TEST_SURVIVAL" in config, \
        "init.md config.py block must declare the optional CRAFT_REQUIRE_TEST_SURVIVAL flag"


# --- Report dir .harness/craft/ documented beside results/ and critiques/ ---

def test_init_lists_craft_dir_under_harness():
    struct = _section_from(INIT_CMD.read_text(), ".harness/", "### 2")
    assert "craft/" in struct, \
        "init.md must list craft/ under the .harness/ directory structure"


def test_harness_reference_documents_craft_report_path():
    content = HARNESS_REF.read_text()
    assert ".harness/craft/" in content, \
        "harness-reference.md must document the .harness/craft/<ticket>.json report path"


def test_harness_reference_documents_craft_stage():
    norm = _normalize(HARNESS_REF.read_text())
    assert "craft" in norm and "gate-lock" in norm.replace("gate lock", "gate-lock"), \
        "harness-reference.md must document the craft stage and its gate-lock"
    assert "ticket" in norm, "harness-reference.md must scope craft polish to ticket mode"


def test_readme_documents_craft_stage():
    content = README.read_text()
    assert ".harness/craft/" in content or "craft polish" in content.lower(), \
        "README.md must describe the craft polish stage"


# --- .gitignore covers .harness/craft/ ---

def test_gitignore_covers_craft_dir():
    content = GITIGNORE.read_text()
    assert ".harness/craft/" in content, \
        ".gitignore must ignore .harness/craft/ (transient, like .harness/results/)"
