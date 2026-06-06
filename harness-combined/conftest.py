from __future__ import annotations

import os
import sys

# The gate runner's modules (`gates`, `server`, `models`) are top-level at the
# plugin root. Put that root on sys.path so the test suite can import them.
sys.path.insert(0, os.path.dirname(__file__))
