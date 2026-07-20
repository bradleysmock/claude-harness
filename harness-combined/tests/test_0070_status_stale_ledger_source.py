# harness-combined/tests/test_0070_status_stale_ledger_source.py
"""Content-verification tests for ticket 0070: status/SKILL.md's Step 1 must
enumerate via the harness-tickets ledger (list-json) as primary source, and
the two files' 'keep in sync' marked blocks must be byte-identical."""
from pathlib import Path

STATUS_PATH = Path("skills/status/SKILL.md")
STALE_PATH = Path("skills/stale/SKILL.md")

START_STATUS = "<!-- shared with stale/SKILL.md — keep in sync (start) -->"
START_STALE = "<!-- shared with status/SKILL.md — keep in sync (start) -->"
END_MARKER = "<!-- keep in sync (end) -->"


def _extract_block(text: str, start_marker: str) -> str:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(END_MARKER, start)
    return text[start:end]


def test_status_step1_enumerates_via_list_json() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    step1 = text[text.index("## Step 1"):text.index("## Step 2")]
    assert "ticket.py\" list-json" in step1
    assert "argument-list subprocess" in step1
    assert "Fallback" in step1


def test_shared_blocks_are_byte_identical() -> None:
    status_text = STATUS_PATH.read_text(encoding="utf-8")
    stale_text = STALE_PATH.read_text(encoding="utf-8")
    status_block = _extract_block(status_text, START_STATUS)
    stale_block = _extract_block(stale_text, START_STALE)
    assert status_block == stale_block
    assert "list-json" in status_block


def test_shared_block_is_ledger_primary_not_scan_primary() -> None:
    # FR-8: list-json is the PRIMARY source; the filesystem scan runs only when
    # list-json itself errors — never the other way around (a scan-primary,
    # ledger-as-fallback-on-empty reading would reproduce the invisibility bug
    # this ticket exists to close).
    status_text = STATUS_PATH.read_text(encoding="utf-8")
    block = _extract_block(status_text, START_STATUS)
    assert "**primary** source" in block
    assert "Fallback (ledger unreachable only)" in block
    # the fallback paragraph must come after the primary-source paragraph
    assert block.index("**primary** source") < block.index("Fallback (ledger unreachable only)")


def test_shared_block_excludes_threshold_content() -> None:
    status_text = STATUS_PATH.read_text(encoding="utf-8")
    block = _extract_block(status_text, START_STATUS)
    assert "stale_threshold_days" not in block


def test_status_still_has_own_threshold_paragraph_outside_block() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    block = _extract_block(text, START_STATUS)
    after = text[text.index(END_MARKER) + len(END_MARKER):]
    assert "stale_threshold_days" not in block
    assert "stale_threshold_days" in after
    assert "default of **7** days" in after or "default of 7 days" in after


def test_stale_step1_precedence_unchanged() -> None:
    text = STALE_PATH.read_text(encoding="utf-8")
    step1 = text[text.index("## Step 1"):text.index("## Step 2")]
    assert "--days N" in step1
    assert "stale_threshold_days" in step1
    assert "Default: 7 days" in step1
