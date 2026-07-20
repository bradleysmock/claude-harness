"""Unit tests for `is_autopilot_mode` (ticket 0066).

`build-ticket.md`'s three lead-facing decision points (score-spec BLOCK,
repair exhaustion, clean build) branch on this predicate instead of prose
"watch for this condition" narration. Mirrors the `should_auto_repair(dry_run)`
precedent in `dry_run.py`: a real, unit-tested Python function, not a
model-interpreted cue.
"""

from __future__ import annotations

import pytest

from mode_branch import is_autopilot_mode


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("autopilot", True),
        ("", False),
        ("interactive", False),
        ("Autopilot", False),
        ("autopilot ", False),
        (" autopilot", False),
        ("autopilot-batch", False),
    ],
)
def test_is_autopilot_mode(mode: str, expected: bool) -> None:
    assert is_autopilot_mode(mode) is expected
