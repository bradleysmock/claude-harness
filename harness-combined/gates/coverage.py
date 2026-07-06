"""Language-agnostic coverage enforcement gate.

Wraps pytest-cov (Python), nyc/c8 (Node.js) and cargo-llvm-cov (Rust) behind a
single ``run_coverage_gate`` entry point. Thresholds are read from a dedicated
``.tickets/_thresholds.yaml`` file; results are written to a machine-readable
``gate-findings.json`` sidecar (and a human-readable ``## Coverage`` section in
``gate-findings.md``) so the ``/deliver`` preflight can enforce them fail-closed.

Design invariants:

* **Skip-safe (NFR-2).** A missing tool, missing base ref, subprocess timeout, or
  unreadable ``_thresholds.yaml`` yields ``passed=True`` with a warning — never a
  crash and never a hard block. This mirrors the ``shutil.which`` skip precedent in
  ``gates/rust.py``'s audit gate.
* **Fail-closed on ambiguity.** A coverage tool that ran but whose output could not
  be parsed is ``passed=False`` (``COVERAGE_PARSE_ERROR``) and its sidecar records
  ``passed: false`` — we never treat "no parseable number" as "coverage is fine".
* **Argument-list subprocess only.** Commands are always built as a list with the
  target directory as a discrete element and executed without a shell.
* **Injectable subprocess seam.** ``_runner`` is used for *both* the current-branch
  and base-branch coverage measurements, so unit tests supply ``CompletedProcess``
  results directly instead of monkeypatching ``subprocess`` at module level.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from models import GateError, GateResult

# ── Error / status codes ──────────────────────────────────────────────────────
COVERAGE_BELOW_THRESHOLD = "COVERAGE_BELOW_THRESHOLD"
COVERAGE_TOOL_MISSING = "COVERAGE_TOOL_MISSING"
COVERAGE_TOOL_TIMEOUT = "COVERAGE_TOOL_TIMEOUT"
COVERAGE_PARSE_ERROR = "COVERAGE_PARSE_ERROR"
COVERAGE_CONFIG_ERROR = "COVERAGE_CONFIG_ERROR"
BASE_MERGE_BASE_FAILED = "BASE_MERGE_BASE_FAILED"
BASE_WORKTREE_FAILED = "BASE_WORKTREE_FAILED"
BASE_COVERAGE_RUN_FAILED = "BASE_COVERAGE_RUN_FAILED"

# language → key in _thresholds.yaml. typescript & javascript share the JS floor.
_THRESHOLD_KEYS: dict[str, str] = {
    "python": "min_coverage_python",
    "typescript": "min_coverage_js",
    "javascript": "min_coverage_js",
    "rust": "min_coverage_rust",
}

# language → coverage tool binaries probed via shutil.which, in preference order.
_TOOL_CANDIDATES: dict[str, list[str]] = {
    "python": ["pytest"],
    "typescript": ["nyc", "c8"],
    "javascript": ["nyc", "c8"],
    "rust": ["cargo-llvm-cov"],
}

# Languages this gate can measure at all (FR-1: Python, Node.js, Rust).
SUPPORTED_LANGUAGES: tuple[str, ...] = ("python", "typescript", "javascript", "rust")

_PY_TOTAL = re.compile(r"^TOTAL\s+(?:\d+\s+){2,}(\d+(?:\.\d+)?)%", re.MULTILINE)
_JS_LINES = re.compile(r"Lines\s*:\s*(\d+(?:\.\d+)?)\s*%")
_JS_STMTS = re.compile(r"Statements\s*:\s*(\d+(?:\.\d+)?)\s*%")
_RUST_TOTAL = re.compile(r"^TOTAL\b.*?(\d+(?:\.\d+)?)%", re.MULTILINE)

_COVERAGE_MD_HEADER = "## Coverage"


class CoverageConfigError(ValueError):
    """Raised when ``_thresholds.yaml`` exists but cannot be parsed as YAML."""


# ── Threshold configuration ───────────────────────────────────────────────────

def load_thresholds(standards_path: Path | str) -> dict[str, int]:
    """Load integer coverage thresholds from ``_thresholds.yaml``.

    Looks for ``_thresholds.yaml`` next to ``standards_path`` (i.e.
    ``Path(standards_path).parent / "_thresholds.yaml"``). An absent file — or a
    file whose top-level YAML is not a mapping — returns ``{}`` (skip all
    enforcement). Unparseable YAML, or a present file we cannot read because
    PyYAML is not installed, raises :class:`CoverageConfigError` so the caller can
    surface a ``COVERAGE_CONFIG_ERROR`` warning and skip (never block).
    """
    path = Path(standards_path).parent / "_thresholds.yaml"
    if not path.exists():
        return {}
    try:
        import yaml  # lazy: PyYAML is optional; only needed when the file exists
    except ImportError as exc:  # pragma: no cover - exercised via a sys.modules stub
        raise CoverageConfigError(
            f"cannot read {path}: PyYAML is not installed"
        ) from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CoverageConfigError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        return {}
    thresholds: dict[str, int] = {}
    for key, value in data.items():
        # bool is a subclass of int — exclude it so `min_coverage_python: true`
        # is not silently read as a threshold of 1.
        if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool):
            thresholds[key] = value
    return thresholds


# ── Tool detection & command construction ─────────────────────────────────────

def _detect_tool(language: str) -> str | None:
    """Return an available coverage tool for ``language``, else None.

    Python coverage is provided by the ``pytest-cov`` *plugin*, not a standalone
    binary — the presence of the ``pytest`` runner says nothing about whether
    ``--cov`` will work. Probe the plugin via ``find_spec`` in the interpreter that
    will run the gate (``sys.executable``) so a project with pytest but no
    pytest-cov *skips* (FR-6 / NFR-2) instead of failing closed on the parse error.
    Node/Rust tools are real executables, so ``shutil.which`` is the right probe.
    """
    if language == "python":
        try:
            return "pytest" if importlib.util.find_spec("pytest_cov") is not None else None
        except (ImportError, ValueError):
            # A broken/half-installed pytest_cov makes find_spec raise; treat that
            # as "no usable coverage tool" and skip (NFR-2 skip-safe), never crash.
            return None
    for name in _TOOL_CANDIDATES.get(language, []):
        if shutil.which(name):
            return name
    return None


def _build_command(language: str, directory: str, tool: str) -> list[str]:
    """Build the coverage command as an argument list (no shell, dir as an element)."""
    directory = str(directory)
    if language == "python":
        # `pytest <dir> --cov=. --cov-report=term-missing` run with cwd=<dir>.
        return [sys.executable, "-m", "pytest", directory, "--cov=.",
                "--cov-report=term-missing", "-q"]
    if language in ("typescript", "javascript"):
        # nyc/c8 wrap the project's own test command; --cwd scopes measurement.
        return [tool, "--reporter=text-summary", "--cwd", directory, "npm", "test", "--silent"]
    if language == "rust":
        return ["cargo", "llvm-cov", "--summary-only",
                "--manifest-path", str(Path(directory) / "Cargo.toml")]
    raise ValueError(f"coverage gate: unsupported language {language!r}")


def _parse_coverage(language: str, output: str) -> float | None:
    """Extract the overall coverage percentage from tool output, or None."""
    if language == "python":
        match = _PY_TOTAL.search(output)
    elif language in ("typescript", "javascript"):
        match = _JS_LINES.search(output) or _JS_STMTS.search(output)
    elif language == "rust":
        match = _RUST_TOTAL.search(output)
    else:
        return None
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:  # pragma: no cover - regex already constrains to a number
        return None


def _proc_output(proc: Any) -> str:
    return (getattr(proc, "stdout", "") or "") + "\n" + (getattr(proc, "stderr", "") or "")


# ── Base-branch delta ─────────────────────────────────────────────────────────

def _git(directory: str, args: list[str], timeout_s: int) -> subprocess.CompletedProcess[str] | None:
    """Run a git subcommand against ``directory``; None on any failure (skip-safe)."""
    try:
        return subprocess.run(
            ["git", "-C", str(directory), *args],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except (subprocess.SubprocessError, OSError):
        return None


def _base_measure(
    language: str, directory: str, tool: str, timeout_s: int, _runner: Callable[..., Any]
) -> float | None:
    """Measure coverage in a base-branch worktree; None if it cannot be measured."""
    cmd = _build_command(language, directory, tool)
    try:
        proc = _runner(cmd, capture_output=True, text=True, cwd=str(directory), timeout=timeout_s)
    except (subprocess.SubprocessError, OSError):
        return None
    return _parse_coverage(language, _proc_output(proc))


def _compute_delta(
    directory: str, language: str, base_ref: str, tool: str, current_pct: float,
    timeout_s: int, _runner: Callable[..., Any], warnings: list[str],
) -> float | None:
    """Coverage delta (current − base) via a non-destructive base-ref worktree.

    Returns ``None`` when the base cannot be located at all (no common ancestor, or
    the base worktree could not be created — e.g. a shallow CI clone); returns
    ``0.0`` when the base worktree exists but its coverage run failed (assume no
    regression rather than fabricating one). The worktree is always removed in
    ``finally``.
    """
    base_commit = _git(directory, ["merge-base", "HEAD", base_ref], timeout_s)
    if base_commit is None or base_commit.returncode != 0 or not base_commit.stdout.strip():
        warnings.append(f"{BASE_MERGE_BASE_FAILED}: no common base commit for ref {base_ref!r}")
        return None
    sha = base_commit.stdout.strip()

    tmp = tempfile.mkdtemp(prefix="harness_cov_base_")
    added = _git(directory, ["worktree", "add", "--detach", tmp, sha], timeout_s)
    if added is None or added.returncode != 0:
        warnings.append(f"{BASE_WORKTREE_FAILED}: could not create base worktree at {sha[:12]}")
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    try:
        base_pct = _base_measure(language, tmp, tool, timeout_s, _runner)
        if base_pct is None:
            warnings.append(f"{BASE_COVERAGE_RUN_FAILED}: base coverage produced no parseable result")
            return 0.0
        return round(current_pct - base_pct, 2)
    finally:
        _git(directory, ["worktree", "remove", "--force", tmp], timeout_s)
        shutil.rmtree(tmp, ignore_errors=True)


# ── Sidecar writers ───────────────────────────────────────────────────────────

def _active_ticket_dir(standards_path: Path | str) -> Path | None:
    """Resolve the active ticket directory from ``.tickets/.active`` next to standards."""
    tickets_dir = Path(standards_path).parent
    try:
        slug = (tickets_dir / ".active").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not slug:
        return None
    ticket_dir = tickets_dir / slug
    return ticket_dir if ticket_dir.is_dir() else None


def _atomic_write_json(path: Path, obj: Any) -> None:
    """Write JSON atomically: tempfile in the same dir, fsync, then os.replace."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _strip_section(text: str, header: str) -> str:
    """Remove an existing markdown section (header line through the next '## ')."""
    out: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if line.strip() == header:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            out.append(line)
    return "".join(out)


def _render_coverage_md(cov: dict[str, Any]) -> str:
    delta = cov["delta"]
    delta_str = f"{delta:+.1f}%" if isinstance(delta, (int, float)) else "n/a"
    threshold = cov["threshold"]
    lines = [
        _COVERAGE_MD_HEADER,
        "",
        f"- Status: {cov['status']}",
        f"- Coverage: {cov['pct']:.1f}% (Δ vs base: {delta_str})",
        f"- Threshold: {threshold if threshold is not None else 'n/a'}",
        f"- Passed: {cov['passed']}",
    ]
    for warning in cov["warnings"]:
        lines.append(f"- Warning: {warning}")
    return "\n".join(lines) + "\n"


def _upsert_coverage_md(path: Path, cov: dict[str, Any]) -> None:
    """Insert or replace the '## Coverage' section in gate-findings.md idempotently."""
    existing = ""
    if path.exists():
        existing = _strip_section(path.read_text(encoding="utf-8"), _COVERAGE_MD_HEADER).rstrip("\n")
    section = _render_coverage_md(cov)
    content = f"{existing}\n\n{section}" if existing else section
    path.write_text(content, encoding="utf-8")


def _write_sidecar(standards_path: Path | str, payload: dict[str, Any]) -> None:
    """Best-effort write of gate-findings.json + gate-findings.md; never raises."""
    ticket_dir = _active_ticket_dir(standards_path)
    if ticket_dir is None:
        return
    try:
        _atomic_write_json(ticket_dir / "gate-findings.json", payload)
        _upsert_coverage_md(ticket_dir / "gate-findings.md", payload["coverage"])
    except OSError:
        # The sidecar is observability; a filesystem hiccup must not fail the gate.
        return


def _finish(
    start: float, standards_path: Path | str, *, passed: bool, pct: float | None,
    delta: float | None, threshold: int | None, status: str, warnings: list[str],
    code: str | None,
) -> GateResult:
    """Assemble the GateResult, write the sidecar, and return."""
    duration_ms = int((time.monotonic() - start) * 1000)
    errors: list[GateError] = []
    if not passed and code:
        errors.append(GateError(
            message=next((w for w in warnings if w.startswith(code)), code),
            file=None, line=None, column=None, code=code, severity="error",
        ))
    for warning in warnings:
        warn_code = warning.split(":", 1)[0]
        if not passed and warn_code == code:
            continue  # already recorded as the blocking error
        errors.append(GateError(
            message=warning, file=None, line=None, column=None,
            code=warn_code, severity="warning",
        ))
    payload = {
        "coverage": {
            "passed": passed,
            "pct": float(pct) if pct is not None else 0.0,
            "delta": float(delta) if delta is not None else None,
            "threshold": int(threshold) if threshold is not None else None,
            "status": status,
            "warnings": list(warnings),
        }
    }
    _write_sidecar(standards_path, payload)
    return GateResult(gate="coverage", passed=passed, errors=errors, duration_ms=duration_ms)


# ── Public entry point ────────────────────────────────────────────────────────

def run_coverage_gate(
    directory: str,
    language: str,
    standards_path: Path | str,
    base_ref: str,
    *,
    timeout_s: int = 300,
    _runner: Callable[..., Any] = subprocess.run,
) -> GateResult:
    """Run the coverage gate for ``language`` against ``directory``.

    Returns a ``GateResult`` with ``gate="coverage"``. Always writes a
    ``gate-findings.json`` sidecar into the active ticket directory. Skip-safe on
    every failure mode except an unparseable-but-real measurement, which is
    fail-closed (``passed=False``).
    """
    start = time.monotonic()
    warnings: list[str] = []
    resolved = str(Path(directory).resolve())  # contain the path before any subprocess

    # 1. Thresholds — absent/other → skip; config error → skip with a warning.
    try:
        thresholds = load_thresholds(standards_path)
    except CoverageConfigError as exc:
        warnings.append(f"{COVERAGE_CONFIG_ERROR}: {exc}")
        return _finish(start, standards_path, passed=True, pct=None, delta=None,
                       threshold=None, status="skipped", warnings=warnings,
                       code=COVERAGE_CONFIG_ERROR)

    key = _THRESHOLD_KEYS.get(language)
    threshold = thresholds.get(key) if key else None
    if threshold is None:
        # No floor configured for this language → skip enforcement (FR-2).
        return _finish(start, standards_path, passed=True, pct=None, delta=None,
                       threshold=None, status="skipped", warnings=warnings, code=None)

    # 2. Tool detection — missing tool skips (FR-6), never blocks.
    tool = _detect_tool(language)
    if tool is None:
        warnings.append(f"{COVERAGE_TOOL_MISSING}: no coverage tool on PATH for {language}")
        return _finish(start, standards_path, passed=True, pct=None, delta=None,
                       threshold=threshold, status="skipped", warnings=warnings,
                       code=COVERAGE_TOOL_MISSING)

    # 3. Measure current coverage.
    cmd = _build_command(language, resolved, tool)
    try:
        proc = _runner(cmd, capture_output=True, text=True, cwd=resolved, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        warnings.append(f"{COVERAGE_TOOL_TIMEOUT}: coverage run exceeded {timeout_s}s")
        return _finish(start, standards_path, passed=True, pct=None, delta=None,
                       threshold=threshold, status="skipped", warnings=warnings,
                       code=COVERAGE_TOOL_TIMEOUT)
    except (subprocess.SubprocessError, OSError) as exc:
        warnings.append(f"{COVERAGE_TOOL_MISSING}: coverage tool failed to launch: {exc}")
        return _finish(start, standards_path, passed=True, pct=None, delta=None,
                       threshold=threshold, status="skipped", warnings=warnings,
                       code=COVERAGE_TOOL_MISSING)

    pct = _parse_coverage(language, _proc_output(proc))
    if pct is None:
        # The tool ran but produced no parseable coverage → fail-closed (FR-5b).
        warnings.append(f"{COVERAGE_PARSE_ERROR}: could not parse {tool} coverage output")
        return _finish(start, standards_path, passed=False, pct=None, delta=None,
                       threshold=threshold, status="error", warnings=warnings,
                       code=COVERAGE_PARSE_ERROR)

    # 4. Delta vs base (best-effort; never blocks on its own).
    delta = _compute_delta(resolved, language, base_ref, tool, pct, timeout_s, _runner, warnings)

    # 5. Enforce the floor.
    passed = pct >= threshold
    if passed:
        return _finish(start, standards_path, passed=True, pct=pct, delta=delta,
                       threshold=threshold, status="passed", warnings=warnings, code=None)
    warnings.append(f"{COVERAGE_BELOW_THRESHOLD}: {pct:.1f}% is below the {threshold}% floor")
    return _finish(start, standards_path, passed=False, pct=pct, delta=delta,
                   threshold=threshold, status="failed", warnings=warnings,
                   code=COVERAGE_BELOW_THRESHOLD)
