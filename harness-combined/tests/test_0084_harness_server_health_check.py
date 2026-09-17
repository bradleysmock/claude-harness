"""Ticket 0084 — `bin/harness-server`'s venv health check probes the real import.

The launcher gated its re-bootstrap on a bare ``import mcp``. That still succeeds
under `mcp` 2.x — only the ``mcp.server.fastmcp`` submodule went away — so a venv
already stuck on 2.x passed the check, was never reinstalled, and crashed at
server start on every launch. Probing the exact import ``server.py`` needs makes
that venv read as broken and self-heal on the next launch.

Covers FR-2 (a fresh bootstrap installs `mcp` < 2.0) and FR-3 / AC-2 / AC-4 (the
check probes the submodule, a broken venv reinstalls, a healthy one is left
alone).

Two tiers:

* **Hermetic** — a hand-built venv seeded with an `mcp` package that has no
  ``server.fastmcp`` submodule, plus a stub ``pip`` inside that venv that records
  its argv instead of reaching the network. This runs the *real* launcher script
  end to end with no index access at all.
* **Network** — the genuine production bootstrap against the real package index.
  It installs the full ``requirements.txt`` into a throwaway venv, which takes far
  longer than the 120 s test-gate ceiling, so it is opt-in via
  ``HARNESS_TEST_NETWORK=1`` and additionally skipped when the index is
  unreachable.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = PLUGIN_ROOT / "bin" / "harness-server"

#: The import `server.py` actually depends on — what the health check must probe.
REQUIRED_IMPORT = "from mcp.server.fastmcp import FastMCP"

#: Printed by the stub server so a test can tell "launcher reached the server"
#: apart from "launcher died in the bootstrap".
SERVER_STARTED_MARKER = "HARNESS_STUB_SERVER_STARTED"

#: Every `"$PY" -c '...'` probe in the launcher.
_PROBE_RE = re.compile(r'"\$PY"\s+-c\s+\'([^\']*)\'')

_NEEDS_BASH = pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")


# ── FR-3 / AC-2: the probe target, read straight off the script ───────────────

def _launcher_probes() -> list[str]:
    return _PROBE_RE.findall(LAUNCHER.read_text(encoding="utf-8"))


def test_fr3_health_check_probes_the_submodule_import() -> None:
    """The launcher's only interpreter probe is the import `server.py` needs."""
    assert _launcher_probes() == [REQUIRED_IMPORT]


def test_ac2_health_check_no_longer_probes_the_bare_package() -> None:
    """A bare `import mcp` is a false negative under 2.x — it must be gone."""
    assert "import mcp" not in _launcher_probes()


def test_fr3_health_check_names_server_py_as_its_source_of_truth() -> None:
    """The probe duplicates `server.py`'s import, so it carries a pointer back.

    Without it the two can drift apart silently and the check goes stale again.
    """
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    probe_line_index = next(
        index
        for index, line in enumerate(launcher_text.splitlines())
        if REQUIRED_IMPORT in line
    )
    comment_block = launcher_text.splitlines()[max(0, probe_line_index - 6) : probe_line_index]
    assert any("server.py" in line and line.lstrip().startswith("#") for line in comment_block)


# ── Hermetic launcher fixtures ────────────────────────────────────────────────

def _site_packages(venv: Path) -> Path:
    matches = sorted(venv.glob("lib/python*/site-packages")) or sorted(
        venv.glob("Lib/site-packages")
    )
    assert matches, f"no site-packages under {venv}"
    return matches[0]


def _write_mcp_package(site_packages: Path, *, with_fastmcp: bool) -> None:
    """Seed an `mcp` package, with or without the `server.fastmcp` submodule.

    Without it, this is the shape `mcp` 2.x presents: ``import mcp`` succeeds and
    ``from mcp.server.fastmcp import FastMCP`` raises ``ModuleNotFoundError``.
    """
    package = site_packages / "mcp"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    if not with_fastmcp:
        return
    server_package = package / "server"
    server_package.mkdir(exist_ok=True)
    (server_package / "__init__.py").write_text("", encoding="utf-8")
    (server_package / "fastmcp.py").write_text("class FastMCP:\n    pass\n", encoding="utf-8")


def _write_stub_pip(site_packages: Path, pip_log: Path) -> None:
    """Install a `pip` that records its argv and repairs `mcp` instead of downloading.

    The launcher shells out to ``"$PY" -m pip ...`` twice during a bootstrap; this
    stands in for both so the hermetic tests never touch an index. A
    requirements install materialises the missing ``mcp.server.fastmcp``, which is
    what a real reinstall of the now-pinned requirements would achieve.
    """
    package = site_packages / "pip"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import pathlib\n"
        "import sys\n"
        "import sysconfig\n"
        "\n"
        f"log_path = pathlib.Path({str(pip_log)!r})\n"
        'with log_path.open("a", encoding="utf-8") as handle:\n'
        '    handle.write(" ".join(sys.argv[1:]) + "\\n")\n'
        "\n"
        'if "install" in sys.argv and "-r" in sys.argv:\n'
        '    server_package = pathlib.Path(sysconfig.get_paths()["purelib"]) / "mcp" / "server"\n'
        "    server_package.mkdir(parents=True, exist_ok=True)\n"
        '    (server_package / "__init__.py").write_text("", encoding="utf-8")\n'
        '    (server_package / "fastmcp.py").write_text(\n'
        '        "class FastMCP:\\n    pass\\n", encoding="utf-8"\n'
        "    )\n",
        encoding="utf-8",
    )


def _build_fake_plugin_root(root: Path, *, venv_has_fastmcp: bool) -> Path:
    """A minimal plugin root holding the real launcher and a pre-seeded venv.

    Returns the path the stub pip appends its argv to — empty (absent) exactly
    when the launcher decided no bootstrap was needed.
    """
    (root / "bin").mkdir(parents=True)
    shutil.copy2(LAUNCHER, root / "bin" / "harness-server")
    (root / "requirements.txt").write_text("mcp>=1.0,<2.0\n", encoding="utf-8")
    (root / "server.py").write_text(
        f"{REQUIRED_IMPORT}\n\nprint({SERVER_STARTED_MARKER!r})\n", encoding="utf-8"
    )

    venv = root / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)],
        check=True,
        capture_output=True,
    )
    site_packages = _site_packages(venv)
    pip_log = root / "pip-calls.log"
    _write_mcp_package(site_packages, with_fastmcp=venv_has_fastmcp)
    _write_stub_pip(site_packages, pip_log)
    return pip_log


def _isolated_env() -> dict[str, str]:
    """The ambient environment minus anything that could leak an outer `mcp`."""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _launch(root: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(root / "bin" / "harness-server")],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_isolated_env(),
        stdin=subprocess.DEVNULL,
    )


# ── AC-4 / FR-3: hermetic self-heal behaviour ─────────────────────────────────

@_NEEDS_BASH
def test_ac4_venv_missing_the_submodule_is_reinstalled_and_then_starts(tmp_path: Path) -> None:
    """A 2.x-shaped venv reads as broken: the launcher reinstalls, then starts clean.

    Before the fix the bare `import mcp` probe passed here, no reinstall ran, and
    the server died on `from mcp.server.fastmcp import FastMCP`.
    """
    root = tmp_path / "plugin"
    pip_log = _build_fake_plugin_root(root, venv_has_fastmcp=False)

    result = _launch(root)

    assert pip_log.is_file(), "broken venv did not trigger a bootstrap"
    assert "install -r" in pip_log.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert SERVER_STARTED_MARKER in result.stdout


@_NEEDS_BASH
def test_healthy_venv_starts_without_a_reinstall(tmp_path: Path) -> None:
    """The corrected probe is not over-eager — a working venv is left alone."""
    root = tmp_path / "plugin"
    pip_log = _build_fake_plugin_root(root, venv_has_fastmcp=True)

    result = _launch(root)

    assert not pip_log.exists(), f"healthy venv was needlessly rebootstrapped: {pip_log.read_text()}"
    assert result.returncode == 0, result.stderr
    assert SERVER_STARTED_MARKER in result.stdout


# ── FR-2 / AC-3: the real bootstrap, against the real index ───────────────────

def _index_reachable() -> bool:
    try:
        socket.create_connection(("pypi.org", 443), timeout=5).close()
    except OSError:
        return False
    return True


_NEEDS_NETWORK = pytest.mark.skipif(
    os.environ.get("HARNESS_TEST_NETWORK") != "1" or not _index_reachable(),
    reason="set HARNESS_TEST_NETWORK=1 with a reachable package index to run "
    "the real bootstrap (far exceeds the 120s test-gate ceiling)",
)

_COPY_IGNORE = shutil.ignore_patterns(
    ".venv", ".git", ".worktrees", ".harness", "__pycache__", "*.pyc",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", "node_modules",
)


@_NEEDS_BASH
@_NEEDS_NETWORK
def test_fr2_fresh_bootstrap_installs_mcp_below_two_and_starts(tmp_path: Path) -> None:
    """No `.venv` at all: bootstrap resolves `mcp` < 2.0 and the server starts.

    This is the production path the ticket exists for — an unbounded `mcp>=1.0`
    resolves to the 2.x line here and the launcher's `exec server.py` dies with
    ``ModuleNotFoundError: No module named 'mcp.server.fastmcp'``.
    """
    root = tmp_path / "plugin"
    shutil.copytree(PLUGIN_ROOT, root, ignore=_COPY_IGNORE, symlinks=True)
    assert not (root / ".venv").exists()

    try:
        result = _launch(root, timeout=900)
        launcher_stderr = result.stderr
    except subprocess.TimeoutExpired as expired:
        # The stdio server blocks rather than exiting; reaching that point is a
        # clean start, so only the bootstrap output matters.
        launcher_stderr = (expired.stderr or b"").decode("utf-8", "replace")
    else:
        assert result.returncode == 0, launcher_stderr

    assert "Traceback" not in launcher_stderr, launcher_stderr
    assert "ModuleNotFoundError" not in launcher_stderr, launcher_stderr

    installed = subprocess.run(
        [
            str(root / ".venv" / "bin" / "python"),
            "-c",
            "import importlib.metadata as metadata; print(metadata.version('mcp'))",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=_isolated_env(),
    ).stdout.strip()
    assert int(installed.split(".")[0]) < 2, f"bootstrap resolved mcp {installed}"
