"""Ticket 0084 — `requirements.txt` bounds `mcp` below the breaking 2.x line.

`mcp` 2.x renamed ``FastMCP`` to ``MCPServer`` and dropped the
``mcp.server.fastmcp`` submodule that ``server.py`` imports, so an unbounded
``mcp>=1.0`` lets a fresh bootstrap resolve to a release the server cannot
import. Covers FR-1 (the pin excludes the 2.x line) and FR-4 (nothing else in
the file moved).

These are file-content assertions only — no network, no venv. The companion
launch-path coverage lives in ``test_0084_harness_server_health_check.py``.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = PLUGIN_ROOT / "requirements.txt"
TICKET_SLUG = "0084-mcp-dependency-unpinned-major-break"

#: The pin FR-1 mandates: still open to 1.x patch/minor, closed to the 2.x line.
PINNED_MCP_LINE = "mcp>=1.0,<2.0"

#: A requirement line for the `mcp` distribution — the name, then whatever
#: delimits it from a version specifier, extra, or environment marker. Anchored
#: so sibling distributions whose names merely start with "mcp" never match.
_MCP_REQUIREMENT_RE = re.compile(r"^mcp(?=$|[\s<>=!~;\[,])")


def _is_mcp_requirement(raw_line: str) -> bool:
    return bool(_MCP_REQUIREMENT_RE.match(raw_line.strip()))


def _mcp_requirement_lines() -> list[str]:
    return [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if _is_mcp_requirement(line)
    ]


# ── FR-1: the pin itself ──────────────────────────────────────────────────────

def test_fr1_mcp_pin_excludes_the_two_x_release_line() -> None:
    """The `mcp` requirement reads exactly the bounded pin."""
    assert _mcp_requirement_lines() == [PINNED_MCP_LINE]


def test_fr1_mcp_is_specified_exactly_once() -> None:
    """One pin, so no second line can quietly re-open the 2.x range."""
    assert len(_mcp_requirement_lines()) == 1


# ── FR-4: nothing else in the file moved ──────────────────────────────────────

def _run_git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(PLUGIN_ROOT), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def _ticket_status_path() -> Path | None:
    """This ticket's `status.md`, whether it is still open or already archived."""
    for tickets_dir in (PLUGIN_ROOT / ".tickets", PLUGIN_ROOT / ".tickets" / "completed"):
        candidate = tickets_dir / TICKET_SLUG / "status.md"
        if candidate.is_file():
            return candidate
    return None


def _approved_commit() -> str | None:
    """The design-approval SHA recorded in `status.md` — the pre-change baseline.

    This is the commit the lead approved, before any implementation was written,
    so `requirements.txt` at that revision is exactly the "before" FR-4 compares
    against.
    """
    status_path = _ticket_status_path()
    if status_path is None:
        return None
    for line in status_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("approved-commit:"):
            return line.split(":", 1)[1].strip() or None
    return None


def _baseline_requirements() -> str | None:
    """`requirements.txt` as of the approved commit, or None if unreachable.

    Returns None — a clean skip rather than a failure — once the ticket branch is
    gone (post-delivery, the recorded SHA no longer resolves). FR-4 constrains
    *this ticket's diff*; it is not a claim about the file for all time, so it
    stops being checkable exactly when the baseline stops existing.
    """
    approved = _approved_commit()
    if approved is None:
        return None
    if _run_git("cat-file", "-e", f"{approved}^{{commit}}").returncode != 0:
        return None
    prefix = _run_git("rev-parse", "--show-prefix")
    if prefix.returncode != 0:
        return None
    blob = _run_git("show", f"{approved}:{prefix.stdout.strip()}requirements.txt")
    return blob.stdout if blob.returncode == 0 else None


def _with_pin_applied(baseline_text: str) -> str:
    """The baseline with only its `mcp` line swapped for the bounded pin."""
    rebuilt: list[str] = []
    for raw_line in baseline_text.splitlines(keepends=True):
        if _is_mcp_requirement(raw_line):
            line_ending = raw_line[len(raw_line.rstrip("\r\n")) :]
            rebuilt.append(PINNED_MCP_LINE + line_ending)
        else:
            rebuilt.append(raw_line)
    return "".join(rebuilt)


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_fr4_only_the_mcp_line_differs_from_the_approved_baseline() -> None:
    """Substituting the pin into the pre-change file reproduces it byte-for-byte."""
    baseline = _baseline_requirements()
    if baseline is None:
        pytest.skip("approved-commit baseline for this ticket is not reachable")

    baseline_pins_mcp = any(_is_mcp_requirement(line) for line in baseline.splitlines())
    assert baseline_pins_mcp, "baseline has no mcp requirement to pin"
    assert REQUIREMENTS.read_text(encoding="utf-8") == _with_pin_applied(baseline)
