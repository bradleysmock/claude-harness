from __future__ import annotations

import os
import sys

# Make the monorepo's src/ importable for root-level tests (e.g. test_preorders.py).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Skip the root-level tests/ directory when pytest is invoked from the monorepo
# root — those tests require dependencies (flock, etc.) not installed here.
# Each subproject's own conftest handles its own test discovery.
collect_ignore_glob = ["tests/*"]
