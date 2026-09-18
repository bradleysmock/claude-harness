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
REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)
#: This plugin's directory as the repo sees it, e.g. "harness-combined" — or ""
#: when the plugin *is* the repo root. `relative_to` yields "." in that case,
#: which would make every `startswith` filter and exemption prefix below match
#: nothing and turn five guards vacuously green.
_PLUGIN_RELATIVE = ROOT.relative_to(REPO_ROOT).as_posix()
PLUGIN_PREFIX = "" if _PLUGIN_RELATIVE == "." else _PLUGIN_RELATIVE
#: `PLUGIN_PREFIX` with its trailing slash, for building repo-relative paths.
#: Needed because `f"{PLUGIN_PREFIX}/x"` would become "/x" at the repo root.
_PLUGIN_PATH_PREFIX = f"{PLUGIN_PREFIX}/" if PLUGIN_PREFIX else ""

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

#: Paths whose old-path references are historical record, not live references.
#: An already-delivered ticket's citation of a module path is a true fact about
#: what it verified at the time; a dated implementation plan is a record of what
#: was proposed. Named explicitly so the exclusions are auditable rather than an
#: artifact of where the sweep happens to start.
_HISTORY_EXEMPT_PREFIXES = (
    f"{_PLUGIN_PATH_PREFIX}.tickets/completed/",
    f"{_PLUGIN_PATH_PREFIX}.tickets/0085-reorganize-root-python-modules/",
    "docs/superpowers/plans/",
)

#: Interpolated raw into the patterns below, with no `re.escape`: every moved
#: module name is a bare Python identifier, so it carries no regex metacharacter.
#: `PLUGIN_PREFIX` is a directory name and does get escaped where it appears in a
#: pattern — an unescaped "." there would match any character and widen the sweep.
_MODULE_ALTERNATION = "|".join(MOVED_MODULES)


def _tracked_files() -> list[str]:
    """Every file git tracks in the whole repository, history exemptions removed.

    Repo-wide, not plugin-wide: `harness-pi/` consumes this plugin in place and
    bakes resolved module paths into its generated prompts, so a sweep anchored
    at the plugin root cannot see its stalest references — the blind spot that
    let four of them survive the migration.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        path
        for path in listing.stdout.split("\0")
        if path and not path.startswith(_HISTORY_EXEMPT_PREFIXES)
    ]


def _read_repo_text(repo_relative_path: str) -> str:
    return (REPO_ROOT / repo_relative_path).read_text(encoding="utf-8", errors="replace")


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
    source = _read_repo_text(f"{_PLUGIN_PATH_PREFIX}lib/server.py")
    assert "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))" in source


# ── FR-3: no live reference points at an old root path ────────────────────────

def test_no_plugin_root_reference_targets_the_old_flat_path() -> None:
    """Scoped to this plugin's own tree: the `${CLAUDE_PLUGIN_ROOT}` token resolves
    to whichever plugin contains the file, so a sibling plugin with its own flat
    `server.py` would read as an offender here and is none of this test's business."""
    stale_reference_pattern = re.compile(rf"CLAUDE_PLUGIN_ROOT}}?/({_MODULE_ALTERNATION})\.py")
    offenders = [
        path
        for path in _tracked_files()
        if path.startswith(_PLUGIN_PATH_PREFIX) and stale_reference_pattern.search(_read_repo_text(path))
    ]
    assert offenders == []


def test_no_resolved_path_anywhere_in_the_repo_targets_the_old_flat_path() -> None:
    """The companion repo-wide sweep, over the *expanded* form.

    `harness-pi/scripts/convert-commands.mjs` rewrites `${CLAUDE_PLUGIN_ROOT}` to
    an absolute harness-combined path when it generates `harness-pi/prompts/*.md`,
    so those references carry no token for the test above to match. This literal
    names this plugin unambiguously wherever it appears, which is why this half
    can safely run over every tracked file.
    """
    assert PLUGIN_PREFIX, "this sweep needs a plugin directory name to match on"
    stale_reference_pattern = re.compile(rf"{re.escape(PLUGIN_PREFIX)}/({_MODULE_ALTERNATION})\.py")
    tracked = _tracked_files()
    assert tracked, "the sweep examined no files — it would pass vacuously"
    offenders = [path for path in tracked if stale_reference_pattern.search(_read_repo_text(path))]
    assert offenders == []


def test_bin_launchers_point_into_lib() -> None:
    launchers = {
        f"{_PLUGIN_PATH_PREFIX}bin/harness-server": "lib/server.py",
        f"{_PLUGIN_PATH_PREFIX}bin/autopilot-watch": "lib/autopilot_watch.py",
        f"{_PLUGIN_PATH_PREFIX}bin/ticket": "lib/ticket.py",
    }
    for launcher, expected_target in launchers.items():
        source = _read_repo_text(launcher)
        assert expected_target in source, f"{launcher} does not exec {expected_target}"


def test_no_bin_script_execs_a_module_at_the_old_root_path() -> None:
    """A module path not preceded by `lib/` is a stale root reference. The
    negative lookbehind is what makes this test meaningful: without it,
    `lib/server.py` contains `/server.py` and every launcher reads as an
    offender whether or not it was migrated."""
    stale_reference_pattern = re.compile(rf"(?<!lib)/({_MODULE_ALTERNATION})\.py")
    offenders = [
        path
        for path in _tracked_files()
        if path.startswith(f"{_PLUGIN_PATH_PREFIX}bin/") and stale_reference_pattern.search(_read_repo_text(path))
    ]
    assert offenders == []


# ── FR-5 / FR-6: Python callers import the package, hooks are untouched ───────

def _bare_imports_of_moved_modules(relative_path: str) -> list[str]:
    """Top-level names this file imports that collide with a moved module.

    Parsed with `ast`, not grepped: a regex over source text cannot tell an
    import statement from the same words inside a docstring or comment, and
    `hooks/stop_full_gate.py` has exactly such a comment.
    """
    tree = ast.parse(_read_repo_text(relative_path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [
                alias.name for alias in node.names if alias.name in MOVED_MODULES
            ]
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and node.module.split(".")[0] in MOVED_MODULES
        ):
            offenders.append(node.module)
    return offenders


def _python_files_under(*prefixes: str) -> list[str]:
    qualified_prefixes = tuple(f"{_PLUGIN_PATH_PREFIX}{prefix}" for prefix in prefixes)
    return [
        path
        for path in _tracked_files()
        if path.endswith(".py") and path.startswith(qualified_prefixes)
    ]


def _bare_import_offenders(*prefixes: str) -> dict[str, list[str]]:
    """Python files under `prefixes`, each mapped to the bare names it imports."""
    return {
        path: bare_imports
        for path in _python_files_under(*prefixes)
        if (bare_imports := _bare_imports_of_moved_modules(path))
    }


def test_no_python_caller_imports_a_moved_module_by_its_bare_name() -> None:
    offenders = _bare_import_offenders(
        "gates/", "tests/", "hooks/", "validators/", "skills/", "lib/", "conftest.py"
    )
    assert offenders == {}


def test_no_llm_facing_call_direction_names_a_moved_module_unqualified() -> None:
    """The class both path-shaped sweeps are blind to.

    Markdown instructions routinely tell the model to `call audit.record(...)`
    without an accompanying import line, so the bare module name is the only
    resolution hint it gets. Those sites carry no `${CLAUDE_PLUGIN_ROOT}` token
    and no directory prefix, so neither sweep above can see them — which is how
    16 of them survived the migration and one more survived the first repair.
    A file that spells `from lib import <module>` has bound the bare name
    legitimately and is exempt.
    """
    bare_module_call_pattern = re.compile(rf"(?<![\w.])({_MODULE_ALTERNATION})\.[a-z_]+\(")
    instruction_dirs = (
        f"{_PLUGIN_PATH_PREFIX}commands/",
        f"{_PLUGIN_PATH_PREFIX}context/",
        f"{_PLUGIN_PATH_PREFIX}skills/",
        "harness-pi/prompts/",
    )
    offenders: dict[str, list[str]] = {}
    for path in _tracked_files():
        if not path.endswith(".md") or not path.startswith(instruction_dirs):
            continue
        text = _read_repo_text(path)
        bare_calls = [
            match.group(0)
            for match in bare_module_call_pattern.finditer(text)
            if f"from lib import {match.group(1)}" not in text
        ]
        if bare_calls:
            offenders[path] = bare_calls
    assert offenders == {}


def test_no_hook_imports_a_moved_module() -> None:
    """FR-6: true before the move and still true after, which is why
    `.claude-plugin/plugin.json`'s hook registration needs no change."""
    offenders = _bare_import_offenders("hooks/")
    assert offenders == {}
