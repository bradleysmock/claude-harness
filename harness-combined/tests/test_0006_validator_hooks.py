"""Prose-check tests for the _standards.md validator pipeline hooks (ticket 0006).

The validator only protects the pipeline if its invocation is wired into the
command prose *before* any `_standards.md` content is loaded into context. These
tests assert the guard call is present in each flow file and, where an
`@.tickets/_standards.md` include exists, that the guard precedes it.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INVOCATION = (
    'python3 "${CLAUDE_PLUGIN_ROOT}/validators/standards_validator.py" '
    ".tickets/_standards.md"
)
INCLUDE = "@.tickets/_standards.md"

PROBLEM = "commands/problem.md"
BUILD_TICKET = "context/flows/build-ticket.md"
BUILD_SPEC = "context/flows/build-spec.md"

HOOKED_FILES = [PROBLEM, BUILD_TICKET, BUILD_SPEC]
# Files that carry an @-include the guard must precede.
FILES_WITH_INCLUDE = [PROBLEM, BUILD_TICKET]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_invocation_present_in_all_three_files() -> None:
    for rel in HOOKED_FILES:
        assert INVOCATION in _read(rel), f"validator invocation missing in {rel}"


def test_guard_precedes_standards_include() -> None:
    # Anchor on the actual load directive ("load it via ..."), not any mention of
    # the include token — the guard prose itself references the include when it
    # explains that it runs before it.
    for rel in FILES_WITH_INCLUDE:
        text = _read(rel)
        guard_at = text.find(INVOCATION)
        # First "load it via" is the standards load (learnings load follows it);
        # the guard prose never uses that phrase, so this pins the real directive
        # regardless of whether the include token is backtick-wrapped.
        load_at = text.find("load it via")
        assert guard_at != -1, f"invocation missing in {rel}"
        assert load_at != -1, f"load directive missing in {rel}"
        assert guard_at < load_at, (
            f"validator invocation must precede the {INCLUDE} load directive in {rel}"
        )


def test_each_file_states_non_zero_exit_halts() -> None:
    for rel in HOOKED_FILES:
        text = _read(rel).lower()
        assert "halt" in text, f"{rel} does not state the guard halts the pipeline"
        assert "non-zero" in text, f"{rel} does not describe the non-zero exit contract"


def test_build_spec_guard_at_step_0_entry() -> None:
    # build-spec (standalone spec mode) has no @-include; assert the guard sits at
    # the Step 0 entry, before the detection logic runs.
    text = _read(BUILD_SPEC)
    guard_at = text.find(INVOCATION)
    detect_at = text.find("Decide by what")
    assert guard_at != -1 and detect_at != -1
    assert guard_at < detect_at, "guard must run before build-spec Step 0 detection"
