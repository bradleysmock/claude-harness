"""Per-language gate `/doctor` (ticket 0022).

Diagnostic-only. Scans a project root for language manifests, looks up each
detected language's required gate tools (sourced from each gate module's
``REQUIRED_TOOLS`` export), probes every tool with ``<tool> --version`` under a
short timeout, and assembles a structured :class:`DoctorReport`. Nothing here
modifies the project or installs anything.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from gates.go import REQUIRED_TOOLS as GO_TOOLS
from gates.python import REQUIRED_TOOLS as PYTHON_TOOLS
from gates.rust import REQUIRED_TOOLS as RUST_TOOLS
from gates.typescript import REQUIRED_TOOLS as TS_TOOLS

# Each tool probe is bounded so a broken install can never hang the command.
PROBE_TIMEOUT_SECONDS = 5


class DoctorError(Exception):
    """Raised for an invalid ``project_root`` (not a directory, or outside the
    allowed root). Raised before any filesystem scan or subprocess probe."""


class ToolStatus(Enum):
    FOUND = "found"
    FOUND_ERROR = "found (error)"
    MISSING = "missing"
    TIMEOUT = "timeout"


@dataclass
class ToolResult:
    name: str
    status: ToolStatus
    version: str | None       # None when missing or timeout
    install_hint: str | None  # non-None only when status is MISSING


@dataclass
class LanguageReport:
    language: str
    manifest: str
    tools: list[ToolResult] = field(default_factory=list)


@dataclass
class DoctorReport:
    languages: list[LanguageReport] = field(default_factory=list)
    any_missing: bool = False  # True if any required tool is MISSING or TIMEOUT


@dataclass(frozen=True)
class LanguageSpec:
    """A supported language: its display name, the manifest filenames that mark
    its presence, and the gate tools to probe for it."""

    language: str
    manifests: tuple[str, ...]
    tools: tuple[str, ...]


# Registry, built from each gate module's REQUIRED_TOOLS export so the tool
# lists never drift from what the gates actually invoke (ticket 0022).
LANGUAGE_SPECS: list[LanguageSpec] = [
    LanguageSpec("Python", ("pyproject.toml", "setup.py", "setup.cfg"), tuple(PYTHON_TOOLS)),
    LanguageSpec("TypeScript", ("package.json",), tuple(TS_TOOLS)),
    LanguageSpec("Rust", ("Cargo.toml",), tuple(RUST_TOOLS)),
    LanguageSpec("Go", ("go.mod",), tuple(GO_TOOLS)),
]

# Actionable install hint per tool, surfaced only when a tool is MISSING.
INSTALL_HINTS: dict[str, str] = {
    "mypy": "pip install mypy",
    "ruff": "pip install ruff",
    "bandit": "pip install bandit",
    "tsc": "npm install -g typescript",
    "eslint": "npm install -g eslint",
    "go": "install Go from https://go.dev/dl/",
    "staticcheck": "go install honnef.co/go/tools/cmd/staticcheck@latest",
    "cargo": "install Rust from https://rustup.rs",
    "clippy": "rustup component add clippy",
}


class _ProbeKind(Enum):
    """How a tool is resolved, so the probe mirrors what the gate actually runs.

    A bare ``which <name>`` mislabels tools the gates invoke indirectly: the
    Python gate runs ``sys.executable -m mypy``, the TypeScript gate ``npx
    tsc``, and ``cargo clippy`` dispatches to the ``cargo-clippy`` shim (bare
    ``clippy`` is never on PATH). ``any_missing`` must predict real gate
    readiness, so each tool declares how to probe it.
    """

    DIRECT = "direct"    # bare executable on PATH; non-zero exit => FOUND_ERROR
    MODULE = "module"    # python -m <tool>; non-resolvable (non-zero) => MISSING
    NPX = "npx"          # npx --no-install <tool>; non-resolvable => MISSING


# Per-tool probe: (resolution kind, argv). ``argv[0]`` is what ``which`` checks
# (except MODULE, which always uses the running interpreter). MODULE/NPX probes
# never fetch or install (``-m`` imports an installed module; ``--no-install``
# forbids npx from downloading), honouring the read-only contract (NFR-3).
_PROBES: dict[str, tuple[_ProbeKind, list[str]]] = {
    "mypy": (_ProbeKind.MODULE, [sys.executable, "-m", "mypy", "--version"]),
    "ruff": (_ProbeKind.MODULE, [sys.executable, "-m", "ruff", "--version"]),
    "bandit": (_ProbeKind.MODULE, [sys.executable, "-m", "bandit", "--version"]),
    "tsc": (_ProbeKind.NPX, ["npx", "--no-install", "tsc", "--version"]),
    "eslint": (_ProbeKind.NPX, ["npx", "--no-install", "eslint", "--version"]),
    "go": (_ProbeKind.DIRECT, ["go", "version"]),
    "staticcheck": (_ProbeKind.DIRECT, ["staticcheck", "--version"]),
    "cargo": (_ProbeKind.DIRECT, ["cargo", "--version"]),
    "clippy": (_ProbeKind.DIRECT, ["cargo-clippy", "--version"]),
}


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _probe_tool(name: str) -> ToolResult:
    """Probe one tool for its version, the way its gate resolves it.

    For PATH executables the ``shutil.which`` fast-path avoids launching a
    subprocess for a tool that is plainly absent.
    """
    kind, command = _PROBES.get(name, (_ProbeKind.DIRECT, [name, "--version"]))
    if kind is not _ProbeKind.MODULE and shutil.which(command[0]) is None:
        return ToolResult(name, ToolStatus.MISSING, None, INSTALL_HINTS.get(name))
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        # Reported present but vanished/broken by the time we exec it.
        return ToolResult(name, ToolStatus.MISSING, None, INSTALL_HINTS.get(name))
    except subprocess.TimeoutExpired:
        return ToolResult(name, ToolStatus.TIMEOUT, None, None)

    version = _first_line((proc.stdout or "") + (proc.stderr or ""))
    if proc.returncode == 0:
        return ToolResult(name, ToolStatus.FOUND, version, None)
    if kind in (_ProbeKind.MODULE, _ProbeKind.NPX):
        # The resolver ran but could not produce the tool (module not
        # importable / not resolvable by npx without a network install) — that
        # is genuinely MISSING, not a mere non-zero from a healthy binary.
        return ToolResult(name, ToolStatus.MISSING, None, INSTALL_HINTS.get(name))
    # A real executable on PATH that exited non-zero — installed, not healthy.
    return ToolResult(name, ToolStatus.FOUND_ERROR, version, None)


def _detect_languages(root: Path) -> list[LanguageReport]:
    reports: list[LanguageReport] = []
    for spec in LANGUAGE_SPECS:
        manifest = next((m for m in spec.manifests if (root / m).is_file()), None)
        if manifest is None:
            continue
        reports.append(
            LanguageReport(
                language=spec.language,
                manifest=manifest,
                tools=[_probe_tool(tool) for tool in spec.tools],
            )
        )
    return reports


def _validate_root(project_root: str, allowed_root: str) -> Path:
    """Resolve and contain external input at the trust boundary.

    Rejects paths that escape ``allowed_root`` and paths that are not real
    directories, before any scan or probe runs (FR-8a).
    """
    resolved = Path(project_root or Path.cwd()).resolve()
    allowed = Path(allowed_root).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError:
        raise DoctorError(
            f"project_root {resolved} is outside the allowed root {allowed}"
        ) from None
    if not resolved.is_dir():
        raise DoctorError(f"project_root is not a directory: {resolved}")
    return resolved


def run_doctor(project_root: str = "", allowed_root: str = "/") -> DoctorReport:
    """Scan ``project_root`` (default: CWD) and report gate-tool availability.

    Raises :class:`DoctorError` for an invalid or out-of-bounds ``project_root``
    before touching the filesystem or launching any subprocess.
    """
    root = _validate_root(project_root, allowed_root)
    languages = _detect_languages(root)
    any_missing = any(
        tool.status in (ToolStatus.MISSING, ToolStatus.TIMEOUT)
        for report in languages
        for tool in report.tools
    )
    return DoctorReport(languages=languages, any_missing=any_missing)


def format_report(report: DoctorReport) -> str:
    """Render a human-readable, per-language table."""
    if not report.languages:
        return "no supported languages detected"

    lines: list[str] = []
    for lang in report.languages:
        lines.append(f"{lang.language}  ({lang.manifest})")
        lines.append(f"  {'TOOL':<14} {'STATUS':<14} VERSION / HINT")
        for tool in lang.tools:
            detail = tool.version or tool.install_hint or ""
            lines.append(f"  {tool.name:<14} {tool.status.value:<14} {detail}")
        lines.append("")

    lines.append(
        "One or more required tools are missing — run the hinted installs above."
        if report.any_missing
        else "All required gate tools are present."
    )
    return "\n".join(lines)
