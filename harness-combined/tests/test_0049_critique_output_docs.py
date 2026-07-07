"""
Content-verification tests for ticket 0049 — move /critique output out of cwd
into .harness/critiques/.

Reads the three affected markdown files and asserts, via structural substrings,
that the skill/docs document the new output location, naming scheme, worktree
rule, ticket pointer, and status listing per spec 0049-critique-output-location-docs.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
CRITIQUE_SKILL = ROOT / "skills" / "critique" / "SKILL.md"
STATUS_SKILL = ROOT / "skills" / "status" / "SKILL.md"
INIT_CMD = ROOT / "commands" / "init.md"
README = ROOT / "README.md"


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

def test_target_files_exist():
    assert CRITIQUE_SKILL.exists(), "skills/critique/SKILL.md must exist"
    assert STATUS_SKILL.exists(), "skills/status/SKILL.md must exist"
    assert INIT_CMD.exists(), "commands/init.md must exist"


# --- FR-1: report destination + naming (critique skill) ---

def test_critique_names_harness_critiques_directory():
    out = _section_from(CRITIQUE_SKILL.read_text(), "## Output Format")
    assert ".harness/critiques/" in out, \
        "Output Format must name .harness/critiques/ as the report destination"


def test_critique_has_no_cwd_critique_md_write_instruction():
    """FR-1 / AC: no instruction to write the report to CRITIQUE.md in cwd."""
    norm = _normalize(_section_from(CRITIQUE_SKILL.read_text(), "## Output Format"))
    # The old positive directive ("write it to CRITIQUE.md in the current working
    # directory") must be gone. A negated mention ("never to CRITIQUE.md ...") is fine.
    assert "write it to critique.md in the current working directory" not in norm, \
        "Skill must not instruct writing the report to CRITIQUE.md in the cwd"
    assert "write the report to critique.md" not in norm, \
        "Skill must not instruct writing the report to CRITIQUE.md"


def test_critique_documents_collision_free_chronological_naming():
    out = _section_from(CRITIQUE_SKILL.read_text(), "## Output Format")
    lower = out.lower()
    assert "<target-slug>" in out and "<yyyy-mm-dd>" in lower, \
        "Naming scheme must include a target slug and a date component"
    assert "<nn>" in lower or "counter" in lower, \
        "Naming scheme must include a counter (or time) suffix"
    assert "chronolog" in lower, "Naming must be documented as sorting chronologically"
    assert "collision" in lower, "Naming must be documented as collision-free on same-day re-runs"


def test_critique_creates_directory_if_absent():
    out = _section_from(CRITIQUE_SKILL.read_text(), "## Output Format")
    lower = out.lower()
    assert "creat" in lower and "critiques" in lower, \
        "Skill must state it creates .harness/critiques/ if absent"


# --- FR-2: never inside a worktree ---

def test_critique_never_writes_inside_worktree():
    out = _section_from(CRITIQUE_SKILL.read_text(), "## Output Format")
    lower = out.lower()
    assert "worktree" in lower and "never" in lower, \
        "Skill must state the report is never written inside a worktree"


# --- FR-3: ticket pointer into critic-findings.md ---

def test_critique_documents_ticket_pointer_rule():
    out = _section_from(CRITIQUE_SKILL.read_text(), "## Output Format")
    assert "critic-findings.md" in out, \
        "Ticket-pointer rule must append to the ticket's critic-findings.md"


def test_critique_pointer_carries_four_fields():
    out = _section_from(CRITIQUE_SKILL.read_text(), "## Output Format").lower()
    for field in ("date", "target", "verdict", "report"):
        assert field in out, f"Ticket pointer must carry the '{field}' field"


# --- FR-1: --comment block follows the report to its new path ---

def test_comment_block_reads_new_path_not_cwd_critique_md():
    content = CRITIQUE_SKILL.read_text()
    assert 'Path("CRITIQUE.md")' not in content, \
        "The --comment code block must not read from CRITIQUE.md in the cwd"


# --- FR-4: status skill lists recent critiques ---

def test_status_lists_recent_critiques():
    content = STATUS_SKILL.read_text()
    assert ".harness/critiques" in content, \
        "Status skill must scan .harness/critiques/"
    lower = content.lower()
    assert "three most recent" in lower, \
        "Status skill must list the three most recent critique reports"
    assert "verdict" in lower, \
        "Status skill must show each report's verdict line"


# --- FR-2 (docs): init documents critiques/ under .harness/ ---

def test_init_lists_critiques_dir_under_harness():
    content = INIT_CMD.read_text()
    struct = _section_from(content, ".harness/", "### 2")
    assert "critiques/" in struct, \
        "init.md must list critiques/ under the .harness/ directory structure"


def test_init_gitignores_harness_state():
    """FR-2: init's .gitignore step must actually ignore .harness/ so critiques/ is
    covered by the same treatment as the rest of the .harness/ state (results/, memory.db)."""
    content = INIT_CMD.read_text()
    step4 = _section_from(content, "### 4", "### 5")
    assert ".harness/" in step4, \
        "init.md's .gitignore step (Step 4) must ignore .harness/ so critiques/ and results/ are covered"


# --- README must describe the new output location, not CRITIQUE.md ---

def test_readme_describes_critiques_directory_not_cwd_file():
    """The feature moved; README must not still advertise /critique writing CRITIQUE.md."""
    content = README.read_text()
    assert "CRITIQUE.md" not in content, \
        "README must not advertise /critique writing CRITIQUE.md (output moved to .harness/critiques/)"
    assert ".harness/critiques/" in content, \
        "README must point /critique output at .harness/critiques/"
