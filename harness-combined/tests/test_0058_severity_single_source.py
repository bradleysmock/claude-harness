"""FR-1..8: single-source the 4-tier severity taxonomy in harness-reference.md.

`find_tier_blocks(text)` matches a "tier-definition block": four distinct tier
lines (BLOCKER/MAJOR/MINOR/OBS) within a 6-line window. A tier line requires the
bold span to close *exactly* at the tier name (bullet or table-cell start, then
`**TIER**`, then an em dash / colon / hyphen / pipe) — this excludes both plain
mentions ("... a BLOCKER finding") and bold spans that extend past the tier name
("**BLOCKER and MAJOR findings are must-fix.**"), so the matcher only fires on
an actual definition line, never on usage.

The tree scan (context/, commands/, skills/, agents/, README.md, CLAUDE.md;
docs/ and .tickets/ excluded as historical/non-loaded) is fail-closed: a missing
or empty scan root, harness-reference absent from the scanned set, or the
pointer-named heading missing from harness-reference each raise loudly rather
than passing vacuously.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import pytest

from gates.critic_finding_parser import _SEVERITIES

ROOT = Path(__file__).parent.parent
HARNESS_REFERENCE = ROOT / "context" / "harness-reference.md"
CRITIC_BRIEF = ROOT / "context" / "critic-brief.md"
CRITIQUE_SKILL = ROOT / "skills" / "critique" / "SKILL.md"

HEADING = "### Severity tiers"
HEADING_TEXT = HEADING.lstrip("#").strip()
TIER_NAMES = ("BLOCKER", "MAJOR", "MINOR", "OBS")
WINDOW = 6

_DIR_ROOTS = ("context", "commands", "skills", "agents")
_FILE_ROOTS = ("README.md", "CLAUDE.md")

_TIER_LINE_RE = re.compile(
    r"^\s*[-|]\s*\*\*(?P<tier>BLOCKER|MAJOR|MINOR|OBS)\*\*(?=\s*[—:\-|])"
)


# --------------------------------------------------------------------------- #
# The matcher under test
# --------------------------------------------------------------------------- #
def find_tier_blocks(text: str) -> list[tuple[int, int, tuple[str, ...]]]:
    """Return (start_line, end_line, tier_names) for each 4-tier block found.

    A block is all four distinct tier names appearing as tier lines within a
    window of WINDOW consecutive lines. 1-indexed line numbers. Non-overlapping:
    once a block's hits are consumed they are not reused in a later block.
    """
    lines = text.splitlines()
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        m = _TIER_LINE_RE.match(line)
        if m:
            hits.append((i, m.group("tier")))

    blocks: list[tuple[int, int, tuple[str, ...]]] = []
    i = 0
    n = len(hits)
    while i < n:
        window_start = hits[i][0]
        last_line: dict[str, int] = {}  # tier name -> line number of its latest hit in this window
        order: list[str] = []
        j = i
        while j < n and hits[j][0] - window_start < WINDOW:
            tier = hits[j][1]
            if tier not in last_line:
                order.append(tier)
            last_line[tier] = hits[j][0]
            j += 1
        if len(last_line) == 4:
            blocks.append((window_start, max(last_line.values()), tuple(order)))
            i = j
        else:
            i += 1
    return blocks


# --------------------------------------------------------------------------- #
# Fail-closed tree scan
# --------------------------------------------------------------------------- #
def _scan_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for d in _DIR_ROOTS:
        root_dir = root / d
        if not root_dir.is_dir():
            raise AssertionError(f"scan root missing: {d}")
        found = sorted(root_dir.rglob("*.md"))
        if not found:
            raise AssertionError(f"scan root contributed zero markdown files: {d}")
        files.extend(found)
    for f in _FILE_ROOTS:
        p = root / f
        if not p.is_file():
            raise AssertionError(f"scan root missing: {f}")
        files.append(p)
    reference = next((f for f in files if f.name == "harness-reference.md"), None)
    if reference is None:
        raise AssertionError("harness-reference.md absent from the scanned set")
    if HEADING not in reference.read_text(encoding="utf-8"):
        raise AssertionError(f"pointer-named heading {HEADING!r} missing from harness-reference")
    return files


# --------------------------------------------------------------------------- #
# FR-1: harness-reference is the sole canonical block
# --------------------------------------------------------------------------- #
def test_fr1_harness_reference_has_exactly_one_canonical_block():
    text = HARNESS_REFERENCE.read_text(encoding="utf-8")
    blocks = find_tier_blocks(text)
    assert len(blocks) == 1, f"expected exactly one block in harness-reference.md, found {len(blocks)}"
    _, _, order = blocks[0]
    assert order == TIER_NAMES, f"canonical block must name all four tiers in order, got {order}"


def test_fr1_blocker_names_checkpoint_not_deliver():
    text = HARNESS_REFERENCE.read_text(encoding="utf-8")
    start, end, _ = find_tier_blocks(text)[0]
    block_text = "\n".join(text.splitlines()[start - 1 : end])
    blocker_line = next(row for row in block_text.splitlines() if "**BLOCKER**" in row)
    assert "checkpoint" in blocker_line.lower(), "BLOCKER line must name checkpoint-or-merge"


def test_fr1_no_deliver_pipeline_tokens_in_block():
    text = HARNESS_REFERENCE.read_text(encoding="utf-8")
    start, end, _ = find_tier_blocks(text)[0]
    block_text = "\n".join(text.splitlines()[start - 1 : end])
    assert "deliver summary" not in block_text.lower(), "block must not carry deliver-pipeline tokens"


# --------------------------------------------------------------------------- #
# FR-2 / FR-3: critic-brief.md and critique/SKILL.md are pointers, not copies
# --------------------------------------------------------------------------- #
def test_fr2_critic_brief_has_no_tier_block_and_points_to_heading():
    text = CRITIC_BRIEF.read_text(encoding="utf-8")
    assert find_tier_blocks(text) == [], "critic-brief.md must not carry its own tier-definition block"
    assert HEADING_TEXT in text, "critic-brief.md must name the severity-tiers heading"
    assert "read that section before producing findings" in text


def test_fr3_critique_skill_has_no_tier_block_and_points_to_heading():
    text = CRITIQUE_SKILL.read_text(encoding="utf-8")
    assert find_tier_blocks(text) == [], "critique/SKILL.md must not carry its own tier-definition block"
    assert HEADING_TEXT in text, "critique/SKILL.md must name the severity-tiers heading"
    assert "read that section before producing findings" in text


# --------------------------------------------------------------------------- #
# FR-4: real-tree scan finds no block outside harness-reference
# --------------------------------------------------------------------------- #
def test_fr4_matcher_hits_four_bullet_snippet():
    snippet = (
        "- **BLOCKER** — a\n"
        "- **MAJOR** — b\n"
        "- **MINOR** — c\n"
        "- **OBS** — d\n"
    )
    assert len(find_tier_blocks(snippet)) == 1


def test_fr4_matcher_hits_four_table_row_snippet():
    snippet = (
        "| Tier | Meaning |\n"
        "|---|---|\n"
        "| **BLOCKER** | a |\n"
        "| **MAJOR** | b |\n"
        "| **MINOR** | c |\n"
        "| **OBS** | d |\n"
    )
    assert len(find_tier_blocks(snippet)) == 1


def test_fr4_real_tree_has_no_block_outside_harness_reference():
    files = _scan_files(ROOT)
    offenders = []
    for f in files:
        if f == HARNESS_REFERENCE:
            continue
        blocks = find_tier_blocks(f.read_text(encoding="utf-8"))
        if blocks:
            offenders.append((f, blocks))
    assert offenders == [], f"tier-definition block found outside harness-reference: {offenders}"


def test_fr4_injected_copy_in_tmp_clone_fails():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for d in _DIR_ROOTS:
            shutil.copytree(ROOT / d, tmp_root / d)
        for f in _FILE_ROOTS:
            shutil.copy(ROOT / f, tmp_root / f)
        injected = tmp_root / "commands" / "_injected_copy.md"
        injected.write_text(
            "- **BLOCKER** — x\n- **MAJOR** — y\n- **MINOR** — z\n- **OBS** — w\n",
            encoding="utf-8",
        )
        files = _scan_files(tmp_root)
        offenders = [
            f for f in files
            if f.name != "harness-reference.md" and find_tier_blocks(f.read_text(encoding="utf-8"))
        ]
        assert injected in offenders


# --------------------------------------------------------------------------- #
# FR-5: canonical-block integrity
# --------------------------------------------------------------------------- #
def test_fr5_canonical_block_with_tier_removed_is_not_detected():
    snippet = "- **BLOCKER** — a\n- **MAJOR** — b\n- **MINOR** — c\n"
    assert find_tier_blocks(snippet) == []


def test_fr5_duplicated_block_in_harness_reference_fails_count():
    text = HARNESS_REFERENCE.read_text(encoding="utf-8")
    doctored = text + "\n\n" + "\n".join(f"- **{t}** — dup" for t in TIER_NAMES) + "\n"
    blocks = find_tier_blocks(doctored)
    assert len(blocks) != 1, "fixture precondition: doctored text must show more than one block"


# --------------------------------------------------------------------------- #
# FR-6: fail-closed scan
# --------------------------------------------------------------------------- #
def _tmp_clone() -> Path:
    tmp_root = Path(tempfile.mkdtemp())
    for d in _DIR_ROOTS:
        shutil.copytree(ROOT / d, tmp_root / d)
    for f in _FILE_ROOTS:
        shutil.copy(ROOT / f, tmp_root / f)
    return tmp_root


def test_fr6_renamed_scan_root_fails_loudly():
    tmp_root = _tmp_clone()
    try:
        shutil.move(str(tmp_root / "context"), str(tmp_root / "context_renamed"))
        with pytest.raises(AssertionError, match="scan root missing"):
            _scan_files(tmp_root)
    finally:
        shutil.rmtree(tmp_root)


def test_fr6_emptied_scan_root_fails_loudly():
    tmp_root = _tmp_clone()
    try:
        shutil.rmtree(tmp_root / "agents")
        (tmp_root / "agents").mkdir()
        with pytest.raises(AssertionError, match="zero markdown files"):
            _scan_files(tmp_root)
    finally:
        shutil.rmtree(tmp_root)


def test_fr6_renamed_heading_fails_loudly():
    tmp_root = _tmp_clone()
    try:
        ref = tmp_root / "context" / "harness-reference.md"
        ref.write_text(ref.read_text(encoding="utf-8").replace(HEADING, "### Renamed"), encoding="utf-8")
        with pytest.raises(AssertionError, match="pointer-named heading"):
            _scan_files(tmp_root)
    finally:
        shutil.rmtree(tmp_root)


def test_fr6_missing_harness_reference_fails_loudly():
    tmp_root = _tmp_clone()
    try:
        (tmp_root / "context" / "harness-reference.md").unlink()
        (tmp_root / "context" / "_placeholder.md").write_text("placeholder\n", encoding="utf-8")
        with pytest.raises(AssertionError, match="harness-reference.md absent"):
            _scan_files(tmp_root)
    finally:
        shutil.rmtree(tmp_root)


# --------------------------------------------------------------------------- #
# FR-7: parser pin
# --------------------------------------------------------------------------- #
def test_fr7_canonical_tier_names_match_parser_severities():
    text = HARNESS_REFERENCE.read_text(encoding="utf-8")
    _, _, order = find_tier_blocks(text)[0]
    assert set(order) == set(_SEVERITIES)


# --------------------------------------------------------------------------- #
# FR-8: usage lines never false-positive
# --------------------------------------------------------------------------- #
def test_fr8_cryptography_panel_severity_convention_not_matched():
    text = (ROOT / "context" / "panels" / "cryptography.md").read_text(encoding="utf-8")
    line = next(row for row in text.splitlines() if "Severity convention" in row)
    assert find_tier_blocks(line) == []


def test_fr8_uswds_panel_severity_defaults_not_matched():
    text = (ROOT / "context" / "panels" / "uswds.md").read_text(encoding="utf-8")
    line = next(row for row in text.splitlines() if "Severity defaults" in row)
    assert find_tier_blocks(line) == []


def test_fr8_build_ticket_must_fix_policy_bullet_not_matched():
    text = (ROOT / "context" / "flows" / "build-ticket.md").read_text(encoding="utf-8")
    line = next(row for row in text.splitlines() if "BLOCKER and MAJOR findings are must-fix" in row)
    assert find_tier_blocks(line) == [], "bold span extending past the tier name must not match"


def test_fr8_review_skill_vocabulary_line_not_matched():
    text = (ROOT / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
    line = next(row for row in text.splitlines() if "canonical 4-tier vocabulary" in row)
    assert find_tier_blocks(line) == []
