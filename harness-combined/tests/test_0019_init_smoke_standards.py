"""
Content-verification tests for commands/init.md — spec 0019-post-merge-smoke-test-init.
Verifies the _standards.md template seeds the three commented-out smoke-test config keys.
"""
from pathlib import Path

INIT_FILE = Path(__file__).parent.parent / "commands" / "init.md"


def _standards_block() -> str:
    """Extract the fenced _standards.md template block from init.md."""
    content = INIT_FILE.read_text()
    start = content.find("#### `.tickets/_standards.md`")
    assert start >= 0, "init.md must contain the _standards.md template block"
    end = content.find("#### `.tickets/_learnings.md`", start)
    return content[start:end] if end >= 0 else content[start:]


def test_init_file_exists():
    assert INIT_FILE.exists(), "commands/init.md must exist"


def test_smoke_section_present():
    block = _standards_block()
    assert "## Post-merge smoke test" in block, \
        "_standards.md template must document a Post-merge smoke test section"


def test_all_three_keys_commented_out():
    block = _standards_block()
    for key in ("# smoke_test_command:", "# smoke_test_mode:", "# smoke_test_timeout:"):
        assert key in block, f"template must contain a commented-out {key} key"


def test_command_key_documents_no_pipes_trust():
    block = _standards_block()
    line = next((ln for ln in block.splitlines() if ln.startswith("# smoke_test_command:")), "")
    assert "shlex.split" in line and "shell=False" in line, \
        "smoke_test_command doc must note shlex.split + shell=False"
    assert "LITERAL" in line, "smoke_test_command doc must note metacharacters pass as literal args"
    assert "lead-curated" in line, "smoke_test_command doc must note it is a trusted lead-curated value"


def test_mode_key_documents_both_modes():
    block = _standards_block()
    line = next((ln for ln in block.splitlines() if ln.startswith("# smoke_test_mode:")), "")
    assert "auto-revert" in line and "default" in line
    assert "warn-only" in line


def test_timeout_key_documents_default_and_max():
    block = _standards_block()
    line = next((ln for ln in block.splitlines() if ln.startswith("# smoke_test_timeout:")), "")
    assert "60" in line and "300" in line, "timeout doc must state default 60 and max 300"


def test_required_sections_still_present():
    block = _standards_block()
    assert "## Language" in block and "## Test strategy" in block, \
        "seeding smoke keys must not disturb the required Language / Test strategy sections"
