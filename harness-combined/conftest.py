from __future__ import annotations

import os
import sys

import pytest

# The gate runner's code lives in two packages at the plugin root: `gates` and
# `lib` (which holds `lib.server`, `lib.models`, and the rest). Put that root on
# sys.path so the test suite can import both by their qualified names.
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture(autouse=True)
def _silence_desktop_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite from firing real OS notifications.

    Ticket 0082 made `autopilot_watch.run_tick` notify on a needs-attention
    outcome, which several ticket-0078 `run_tick` tests now reach incidentally —
    without this, running the suite on a desktop pops a notification per test.
    Tests that exercise the notifier itself hold a module-level reference to the
    real function captured at import time and call that instead.
    """
    from lib import autopilot_watch

    monkeypatch.setattr(autopilot_watch, "_notify_desktop", lambda number, reason: None)
