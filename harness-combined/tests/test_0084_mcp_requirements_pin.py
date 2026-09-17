"""Ticket 0084 — `requirements.txt` bounds `mcp` below the breaking 2.x line.

`mcp` 2.x renamed ``FastMCP`` to ``MCPServer`` and dropped the
``mcp.server.fastmcp`` submodule that ``server.py`` imports, so an unbounded
``mcp>=1.0`` lets a fresh bootstrap resolve to a release the server cannot
import. Covers FR-1 (the pin excludes the 2.x line) and FR-4 (nothing else in
the file moved).

On FR-4: "byte-for-byte unchanged" is a claim about *this ticket's diff*, and a
diff has no durable representation in the suite — any baseline a test could hold
either dies with the branch after the delivery squash or has to be re-edited on
every later dependency change. So FR-4 splits in two. The byte-for-byte half is
discharged against the review diff, which shows a single changed line. The half
that stays worth asserting forever is below: the edit left no duplicate pin
behind. That is the one piece of collateral damage with teeth — a bounded `mcp`
added *alongside* the unbounded one rather than replacing it re-opens the very
range FR-1 exists to close, and no other assertion here would notice.

These are file-content assertions only — no network, no venv. The companion
launch-path coverage lives in ``test_0084_harness_server_health_check.py``.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = PLUGIN_ROOT / "requirements.txt"

#: The pin FR-1 mandates: still open to 1.x patch/minor, closed to the 2.x line.
PINNED_MCP_LINE = "mcp>=1.0,<2.0"

#: PEP 503 form of the name under test. Every name read off the file is put
#: through the same normalisation, so spelling variants of one distribution
#: (`types-PyYAML` / `types_pyyaml`) compare equal rather than reading as two.
MCP_DISTRIBUTION = canonicalize_name("mcp")

#: pip starts a comment at a `#` that opens a line or follows whitespace, and
#: `Requirement` rejects a line carrying one. Stripped before parsing so a legal
#: inline comment stays legal here. The leading-whitespace anchor is load-bearing:
#: it leaves a URL fragment such as `... #egg=name` attached to its requirement.
_INLINE_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")


def _requirement_lines() -> list[str]:
    """Every line that declares a dependency — comments, options and blanks dropped.

    Installer options (`-r`, `--index-url`) name no distribution, so they go with
    the comments rather than to ``Requirement``, which parses dependency syntax
    only and would raise on them.
    """
    uncommented = (
        _INLINE_COMMENT_RE.sub("", line).strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    )
    return [line for line in uncommented if line and not line.startswith("-")]


def _mcp_requirement_lines() -> list[str]:
    return [
        line
        for line in _requirement_lines()
        if canonicalize_name(Requirement(line).name) == MCP_DISTRIBUTION
    ]


# ── FR-1: the pin itself ──────────────────────────────────────────────────────

def test_fr1_mcp_pin_excludes_the_two_x_release_line() -> None:
    """The `mcp` requirement reads exactly the bounded pin."""
    assert _mcp_requirement_lines() == [PINNED_MCP_LINE]


def test_fr1_pin_admits_one_x_and_excludes_two_x() -> None:
    """The specifier resolves the way it reads — 1.x in, 2.x out.

    A pin can look plausible and still be wrong: `<2` and `<2.0` and `!=2.*`
    differ in what they admit. Asserting through the resolver's own semantics
    catches a well-spelled pin that does not actually exclude the release line
    this ticket exists to keep out.
    """
    bounds = Requirement(_mcp_requirement_lines()[0]).specifier

    assert "1.28.1" in bounds, "the 1.x release the harness runs on must stay installable"
    assert "1.99.0" in bounds, "1.x minor/patch updates must keep flowing"
    assert "2.0.0" not in bounds
    assert "2.2.0" not in bounds, "the release that broke the server"


# ── FR-4: the edit disturbed nothing around it ────────────────────────────────

def test_fr4_no_distribution_is_pinned_twice() -> None:
    """One line per dependency — nothing needs updating when a dependency is added.

    Guards a bounded `mcp` pin added *alongside* the unbounded one rather than
    replacing it, which would re-open the 2.x range FR-1 exists to close, and
    more generally any duplicate left behind by an edit to this file.
    """
    lines_per_distribution = Counter(
        canonicalize_name(Requirement(line).name) for line in _requirement_lines()
    )
    duplicated = sorted(
        name for name, line_count in lines_per_distribution.items() if line_count > 1
    )
    assert duplicated == []
