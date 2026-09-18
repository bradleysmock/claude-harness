"""Layout and reference-integrity tests for the `lib/` subpackage (ticket 0085).

The 18 implementation modules that used to sit flat at the plugin root now live
in `lib/`. Nothing about that move is enforced by the interpreter: a module left
behind at the root still imports fine, and a flow whose `${CLAUDE_PLUGIN_ROOT}`
invocation string still omits the `lib/` segment fails only when a lead runs that
flow, long after delivery. These tests pin both halves — where the modules live,
and that every live reference points at the new location — so a regression
surfaces in the suite instead of in someone's session.

Note this module quotes no old-path literal anywhere, deliberately: the sweep
below scans every tracked file, this one included, so an illustrative example
here would read as a real stale reference and fail the test it illustrates.

Historical records are deliberately exempt: `.tickets/completed/` documents what
an already-delivered ticket verified at the time, and ticket 0085's own artifacts
narrate this move using the old paths as their subject.
"""

from __future__ import annotations

import ast
import asyncio
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: The modules relocated by ticket 0085, as enumerated in its requirements FR-1.
MOVED_MODULES = (
    "audit",
    "autopilot_watch",
    "context_rank",
    "dag",
    "dry_run",
    "flaky_detect",
    "health",
    "learnings",
    "memory",
    "mode_branch",
    "models",
    "panel_detect",
    "sarif_output",
    "server",
    "spec_coverage",
    "ticket",
    "ticket_deps",
    "ticket_templates",
)

#: The 13 MCP tools `lib/server.py` registers. Pinned by name, not by count, so
#: a rename that keeps the count constant still fails.
EXPECTED_MCP_TOOLS = frozenset({
    "artifact",
    "checkpoint",
    "commit_lint",
    "context_fetch",
    "dag_load",
    "doctor",
    "gate_run",
    "gate_run_on_dir",
    "gate_run_red_check",
    "harness_status",
    "memory",
    "repair_run",
    "spec_load",
})

#: Ticket directories whose old-path references are historical record.
_HISTORY_EXEMPT = (".tickets/completed/", ".tickets/0085-reorganize-root-python-modules/")

_MODULE_ALTERNATION = "|".join(MOVED_MODULES)


def _tracked_files() -> list[str]:
    """Every file git tracks under the plugin root, history exemptions removed."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        path
        for path in listing.stdout.split("\0")
        if path and not path.startswith(_HISTORY_EXEMPT)
    ]


def _text_of(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8", errors="replace")


# ── FR-1: where the modules live ──────────────────────────────────────────────

def test_only_conftest_remains_at_the_plugin_root() -> None:
    root_modules = sorted(path.name for path in ROOT.glob("*.py"))
    assert root_modules == ["conftest.py"]


def test_lib_is_a_package() -> None:
    assert (ROOT / "lib" / "__init__.py").is_file()


@pytest.mark.parametrize("module_name", MOVED_MODULES)
def test_each_moved_module_lives_in_lib(module_name: str) -> None:
    assert (ROOT / "lib" / f"{module_name}.py").is_file()


# ── FR-2 / FR-4: the package imports cleanly ──────────────────────────────────

def test_every_moved_module_imports_from_a_fresh_interpreter() -> None:
    """A subprocess, not an in-process import: the suite's own conftest has
    already primed `sys.modules`, which would mask a broken import chain."""
    program = "import " + ", ".join(f"lib.{name}" for name in MOVED_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_server_registers_the_same_thirteen_mcp_tools() -> None:
    """Asks the FastMCP registry itself rather than inspecting the module's
    namespace: `@mcp.tool()` returns the undecorated function, so a plain
    `vars()` scan cannot tell a registered tool from any other helper."""
    from lib import server

    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_MCP_TOOLS


def test_server_puts_the_plugin_root_on_sys_path_not_its_own_directory() -> None:
    """`lib/server.py` runs as a script (`bin/harness-server` execs it), where
    `sys.path[0]` is `lib/`. It must add the *parent* so `lib.*` and `gates.*`
    both resolve; the pre-move `Path(__file__).parent` would add `lib/` twice."""
    source = _text_of("lib/server.py")
    assert "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))" in source


# ── FR-3: no live reference points at an old root path ────────────────────────

def test_no_plugin_root_reference_targets_the_old_flat_path() -> None:
    stale = re.compile(rf"CLAUDE_PLUGIN_ROOT}}?/({_MODULE_ALTERNATION})\.py")
    offenders = [path for path in _tracked_files() if stale.search(_text_of(path))]
    assert offenders == []


def test_bin_launchers_point_into_lib() -> None:
    launchers = {
        "bin/harness-server": "lib/server.py",
        "bin/autopilot-watch": "lib/autopilot_watch.py",
        "bin/ticket": "lib/ticket.py",
    }
    for launcher, expected_target in launchers.items():
        source = _text_of(launcher)
        assert expected_target in source, f"{launcher} does not exec {expected_target}"


def test_no_bin_script_execs_a_module_at_the_old_root_path() -> None:
    """A module path not preceded by `lib/` is a stale root reference. The
    negative lookbehind is what makes this test meaningful: without it,
    `lib/server.py` contains `/server.py` and every launcher reads as an
    offender whether or not it was migrated."""
    stale = re.compile(rf"(?<!lib)/({_MODULE_ALTERNATION})\.py")
    offenders = [
        path
        for path in _tracked_files()
        if path.startswith("bin/") and stale.search(_text_of(path))
    ]
    assert offenders == []


# ── FR-5 / FR-6: Python callers import the package, hooks are untouched ───────

def _bare_imports_of_moved_modules(relative_path: str) -> list[str]:
    """Top-level names this file imports that collide with a moved module.

    Parsed with `ast`, not grepped: a regex over source text cannot tell an
    import statement from the same words inside a docstring or comment, and
    `hooks/stop_full_gate.py` has exactly such a comment.
    """
    tree = ast.parse(_text_of(relative_path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [
                alias.name for alias in node.names if alias.name in MOVED_MODULES
            ]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] in MOVED_MODULES:
                offenders.append(node.module)
    return offenders


def _python_files_under(*prefixes: str) -> list[str]:
    return [
        path
        for path in _tracked_files()
        if path.endswith(".py") and path.startswith(prefixes)
    ]


def test_no_python_caller_imports_a_moved_module_by_its_bare_name() -> None:
    callers = _python_files_under(
        "gates/", "tests/", "hooks/", "validators/", "skills/", "lib/", "conftest.py"
    )
    offenders = {
        path: bare
        for path in callers
        if (bare := _bare_imports_of_moved_modules(path))
    }
    assert offenders == {}


def test_no_hook_imports_a_moved_module() -> None:
    """FR-6: true before the move and still true after, which is why
    `.claude-plugin/plugin.json`'s hook registration needs no change."""
    offenders = {
        path: bare
        for path in _python_files_under("hooks/")
        if (bare := _bare_imports_of_moved_modules(path))
    }
    assert offenders == {}
