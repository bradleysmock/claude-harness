"""
Content-verification tests for ticket 0050 — testability rubric (WARN tier).

Verifies context/score-spec.md documents the seventh, WARN-only "FR testability"
check (FR-1), maps it to WARN with the BLOCK set unchanged (FR-2), that
commands/refine.md surfaces testability WARNs (FR-3), that the report template
carries the per-FR testability line (FR-4), and that the check ships two worked
examples (NFR-2).
"""
from pathlib import Path

REPO = Path(__file__).parent.parent
SCORE_SPEC = REPO / "context" / "score-spec.md"
REFINE = REPO / "commands" / "refine.md"

ORIGINAL_BLOCK_CHECKS = [
    "FR count",
    "Imperative language",
    "Test-plan coverage",
    "No placeholders",
]


def _section(content: str, start: str, end: str | None = None) -> str:
    i = content.find(start)
    assert i >= 0, f"Section '{start}' not found"
    if end is None:
        return content[i:]
    j = content.find(end, i + len(start))
    return content[i:j] if j >= 0 else content[i:]


# --- files exist ---

def test_target_files_exist():
    assert SCORE_SPEC.exists(), "context/score-spec.md must exist"
    assert REFINE.exists(), "commands/refine.md must exist"


# --- FR-1: seventh check present, per-FR, judging actor/action/outcome ---

def test_fr1_testability_check_present():
    content = SCORE_SPEC.read_text()
    checks = _section(content, "## Checks", "## Output")
    assert "FR testability" in checks, \
        "score-spec.md Checks must add an 'FR testability' check"
    assert "7. **FR testability**" in checks, \
        "FR testability must be the seventh numbered check"


def test_fr1_check_is_per_fr_and_reports_reason():
    content = SCORE_SPEC.read_text()
    checks = _section(content, "## Checks", "## Output")
    lower = checks.lower()
    assert "each" in lower and "functional requirement" in lower, \
        "Testability check must be applied per functional requirement"
    # judges derivability of a failing test from the FR sentence alone
    assert "actor" in lower and "action" in lower and "observable outcome" in lower, \
        "Testability check must judge concrete actor, action, and observable outcome"
    assert "reason" in lower, \
        "Testability check must report a one-line reason per flagged FR"


# --- FR-2: WARN-only mapping; original four BLOCK checks unchanged ---

def test_fr2_testability_maps_to_warn():
    content = SCORE_SPEC.read_text()
    severity = _section(content, "**Severity per check**", None)
    warn_line = next(
        (ln for ln in severity.splitlines() if "WARN if failing" in ln), ""
    )
    assert "FR testability" in warn_line, \
        "Severity section must map FR testability to WARN"


def test_fr2_block_set_unchanged():
    content = SCORE_SPEC.read_text()
    severity = _section(content, "**Severity per check**", None)
    # Scan EVERY BLOCK-if-failing line — a second such line granting testability
    # BLOCK authority must be caught even if the original line is left intact.
    block_lines = [ln for ln in severity.splitlines() if "BLOCK if failing" in ln]
    assert block_lines, "Severity section must retain a BLOCK-if-failing line"
    combined = " ".join(block_lines)
    for check in ORIGINAL_BLOCK_CHECKS:
        assert check in combined, \
            f"Original BLOCK check '{check}' must remain in the BLOCK line(s)"
    for ln in block_lines:
        assert "testability" not in ln.lower(), \
            "FR testability must NOT be granted BLOCK authority in any severity line"


def test_fr2_check_declares_warn_only():
    content = SCORE_SPEC.read_text()
    checks = _section(content, "## Checks", "## Output")
    lower = checks.lower()
    assert "warn" in lower, "Testability check text must state it is WARN-only"
    assert "never" in lower or "only ever" in lower or "no block" in lower, \
        "Testability check must state it never blocks the verdict"


# --- FR-3: refine Step 2 surfaces testability WARNs ---

def test_fr3_refine_surfaces_testability_warns():
    content = REFINE.read_text()
    step2 = _section(content, "2. Proactively surface", "3.")
    lower = step2.lower()
    assert "testability" in lower, \
        "refine.md Step 2 must surface testability-flagged FRs"
    assert "warn" in lower, \
        "refine.md Step 2 must reference the score-spec testability WARN"


# --- FR-4: report template carries the per-FR testability line ---

def test_fr4_report_template_has_testability_line():
    content = SCORE_SPEC.read_text()
    output = _section(content, "## Output", "**Verdict rules**")
    assert "FR testability" in output, \
        "Output template must include the FR testability line"
    assert "FR-<n>" in output or "FR-<n>:" in output, \
        "Output template must show the per-FR testability reason line"
    # The template status enumeration for FR testability must never offer BLOCK.
    tmpl_line = next(
        (ln for ln in output.splitlines()
         if "FR testability" in ln and ln.strip().startswith("[")),
        "",
    )
    assert tmpl_line, "Output must have a bracketed status line for FR testability"
    assert "[PASS|WARN]" in tmpl_line, \
        "FR testability template line must enumerate only PASS|WARN"
    assert "BLOCK" not in tmpl_line, \
        "FR testability template line must NOT offer a BLOCK status"


# --- NFR-2: two worked examples (one passing, one flagged) ---

def test_nfr2_two_worked_examples():
    content = SCORE_SPEC.read_text()
    checks = _section(content, "## Checks", "## Output")
    lower = checks.lower()
    assert "worked example" in lower, \
        "Testability check must include worked examples"
    # Anchor each example to its own bullet so deleting one is caught — the bare
    # words "passes"/"flagged" also occur in the check's ordinary prose.
    assert "**Passes**" in checks, \
        "A passing worked-example bullet (**Passes**) must be present"
    assert "**Flagged**" in checks, \
        "A flagged worked-example bullet (**Flagged**) must be present"
    assert "Reason:" in checks, \
        "The flagged worked example must carry a one-line Reason"
