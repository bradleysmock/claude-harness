"""Explicit `MODE` branch predicate for autopilot interception (ticket 0066).

`autopilot-ticket.md` sets `MODE=autopilot` before delegating to
`build-ticket.md`, which evaluates `is_autopilot_mode(MODE)` at its three
lead-facing decision points (score-spec BLOCK, repair exhaustion, clean
build) instead of narrating "watch for this condition" prose. Mirrors the
`should_auto_repair(dry_run)` precedent in `dry_run.py`: a real,
unit-tested predicate, not a model-interpreted cue.
"""

from __future__ import annotations

AUTOPILOT_MODE = "autopilot"


def is_autopilot_mode(mode: str) -> bool:
    """True only when `mode` is exactly `"autopilot"`.

    A caller that never sets `MODE` passes `""` (never `None`), which —
    like any other value (e.g. `"interactive"`) — returns `False`: today's
    fail-closed default for interactive `/build`, `/write-spec`, and any
    other caller that never opts into autopilot mode.
    """
    return mode == AUTOPILOT_MODE
