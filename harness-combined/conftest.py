from __future__ import annotations

import os
import sys

import pytest

# The gate runner's modules (`gates`, `server`, `models`) are top-level at the
# plugin root. Put that root on sys.path so the test suite can import them.
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
    import autopilot_watch

    monkeypatch.setattr(autopilot_watch, "_notify_desktop", lambda number, reason: None)
