"""Bandit adapter for the SAST gate (ticket 0025).

Runs Bandit recursively over the worktree as an argument list with ``-f json``,
only when the worktree contains Python. Exit-code disambiguation is the crux:
Bandit exits 1 both for "findings present" and for some invocation faults, so the
JSON schema is validated to tell them apart (NFR-3, fail closed). A missing tool
or a non-Python project skips cleanly (FR-8/FR-2); a timeout is a partial-results
warning (NFR-1).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from gates.sast_models import Finding, ScanResult, map_severity
from gates.sast_util import relativize, resolve_contained, tool_available

logger = logging.getLogger(__name__)

#: Single source of truth for directories both the Python-file probe and the
#: Bandit ``--exclude`` argument ignore (keep the two in lockstep — M-3).
_SKIP_DIR_NAMES = frozenset({".venv", "venv", "node_modules", ".git", "__pycache__"})
_SKIP_DIRS = ",".join(sorted(_SKIP_DIR_NAMES))


def _has_python_files(worktree_dir: Path) -> bool:
    """True if the worktree contains at least one ``.py`` file (FR-2)."""
    for path in worktree_dir.rglob("*.py"):
        if set(path.parts) & _SKIP_DIR_NAMES:
            continue
        return True
    return False


def discover_bandit_config(project_root: Path) -> Path | None:
    """Return a contained ``bandit.ini`` in ``project_root``, else ``None``."""
    return resolve_contained(project_root / "bandit.ini", project_root)


def _bandit_command(worktree_dir: Path, config: Path | None) -> list[str]:
    cmd = [
        sys.executable, "-m", "bandit", "-r", str(worktree_dir),
        "-f", "json", "-q", "--exclude", _SKIP_DIRS,
    ]
    if config is not None:
        cmd += ["-c", str(config)]
    return cmd


def _parse_bandit_json(stdout: str, worktree: Path) -> tuple[list[Finding], list[str]]:
    """Parse Bandit JSON into findings; collect out-of-tree path warnings."""
    findings: list[Finding] = []
    warnings: list[str] = []
    payload: dict[str, Any] = json.loads(stdout)  # caller guards JSONDecodeError
    for result in payload.get("results", []):
        try:
            raw_path = result["filename"]
            rule_id = result.get("test_id", "bandit-unknown")
            native = result.get("issue_severity", "LOW")
            line = result.get("line_number")
            message = result.get("issue_text") or rule_id
        except (KeyError, TypeError):
            continue
        rel = relativize(raw_path, worktree)
        if rel is None:
            warnings.append(f"SAST tool reported a path outside worktree — skipped: {raw_path}")
            continue
        findings.append(Finding(
            file=rel,
            line=int(line) if isinstance(line, int) else None,
            rule_id=str(rule_id),
            severity=map_severity("bandit", str(native)),
            message=str(message).splitlines()[0] if message else str(rule_id),
            tool="bandit",
        ))
    return findings, warnings


def run_bandit(worktree_dir: Path, project_root: Path, *, timeout: int = 120) -> ScanResult:
    """Run Bandit over ``worktree_dir`` and return a :class:`ScanResult`.

    Exit-code disambiguation (three branches):
      * exit 0 → clean, no findings;
      * exit 1 with valid JSON containing a ``results`` key → parse findings;
      * exit 1 with unparseable / missing-``results`` JSON, OR exit ≥ 2 →
        invocation error → fail closed (``invocation_error=True``).
    """
    worktree_dir = Path(worktree_dir)
    project_root = Path(project_root)
    if not tool_available("bandit"):
        return ScanResult(warnings=["SAST skipped: bandit not installed"], skipped=True)
    if not _has_python_files(worktree_dir):
        return ScanResult(warnings=["bandit skipped: no Python files in scan target"], skipped=True)

    config = discover_bandit_config(project_root)
    cmd = _bandit_command(worktree_dir, config)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return ScanResult(warnings=[f"PARTIAL SCAN: bandit timed out at {timeout}s — findings may be incomplete"])
    except OSError as exc:
        logger.warning("bandit invocation failed: %s", exc)
        return ScanResult(warnings=[f"SAST skipped: bandit could not be executed ({exc})"], skipped=True)

    if proc.returncode >= 2:
        return ScanResult(
            warnings=[f"SAST INVOCATION-ERROR: bandit exited {proc.returncode}: "
                      f"{(proc.stderr or proc.stdout)[:200].strip()}"],
            invocation_error=True,
        )
    if proc.returncode == 0:
        return ScanResult()
    # exit 1: either findings-present (valid JSON w/ 'results') or a fault.
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return ScanResult(
            warnings=["SAST INVOCATION-ERROR: bandit exited 1 with unparseable JSON output"],
            invocation_error=True,
        )
    if not isinstance(payload, dict) or "results" not in payload:
        return ScanResult(
            warnings=["SAST INVOCATION-ERROR: bandit exited 1 without a 'results' key"],
            invocation_error=True,
        )
    findings, warnings = _parse_bandit_json(proc.stdout, worktree_dir)
    return ScanResult(findings=findings, warnings=warnings)
