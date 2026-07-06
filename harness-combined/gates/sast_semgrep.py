"""Semgrep adapter for the SAST gate (ticket 0025).

Invokes Semgrep as an argument list (never a shell string), parses its JSON, and
normalises each result into a :class:`gates.sast_models.Finding`. Config
discovery prefers a project-owned ``.semgrep.yml`` (contained within the project
root) and falls back to the ``p/default`` ruleset with a floating-ruleset
warning (FR-1). A missing binary is a graceful skip (FR-8); a timeout is a
partial-results warning, not a hard failure (NFR-1).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from gates.sast_models import Finding, ScanResult, map_severity
from gates.sast_util import relativize, resolve_contained, tool_available

logger = logging.getLogger(__name__)

#: Cap per-file scan cost so a large blob cannot blow the 120 s budget (NFR-1).
_MAX_TARGET_BYTES = "1000000"


def discover_semgrep_config(project_root: Path) -> tuple[Path | None, list[str]]:
    """Locate a contained ``.semgrep.yml``; return ``(path_or_None, warnings)``.

    When the file is absent or escapes ``project_root`` (e.g. a symlink), returns
    ``None`` and a floating-ruleset warning so the caller uses ``p/default``.
    """
    candidate = project_root / ".semgrep.yml"
    contained = resolve_contained(candidate, project_root)
    if contained is not None:
        return contained, []
    warning = (
        "SAST: no project-owned .semgrep.yml found (or it escapes the project "
        "root); using the floating 'p/default' ruleset — pin .semgrep.yml to "
        "stabilise findings"
    )
    return None, [warning]


def _parse_semgrep_json(stdout: str, worktree: Path) -> tuple[list[Finding], list[str], int]:
    """Parse Semgrep ``--json`` stdout into findings; collect path warnings.

    Returns ``(findings, warnings, error_count)`` where ``error_count`` is the
    length of Semgrep's own ``errors`` array (populated on rule/config failures
    even on some exit-1 paths). Defensive: malformed JSON or missing keys yield
    no findings rather than raising. A result whose path escapes the worktree is
    discarded with a warning.
    """
    findings: list[Finding] = []
    warnings: list[str] = []
    if not stdout.strip():
        return findings, warnings, 0
    try:
        payload: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError:
        warnings.append("SAST: could not parse Semgrep JSON output — no Semgrep findings recorded")
        return findings, warnings, 0
    # Count only fatal (`level == "error"`) entries — Semgrep also records
    # recoverable per-file parse issues here with `level == "warn"`, which must
    # not fail the whole gate (M-4).
    tool_errors = payload.get("errors") or []
    error_count = (
        sum(1 for e in tool_errors if isinstance(e, dict) and e.get("level") == "error")
        if isinstance(tool_errors, list) else 0
    )
    for result in payload.get("results", []):
        try:
            raw_path = result["path"]
            rule_id = result.get("check_id", "semgrep-unknown")
            native = result.get("extra", {}).get("severity", "INFO")
            line = result.get("start", {}).get("line")
            message = result.get("extra", {}).get("message") or rule_id
        except (KeyError, TypeError, AttributeError):
            continue
        rel = relativize(raw_path, worktree)
        if rel is None:
            warnings.append(f"SAST tool reported a path outside worktree — skipped: {raw_path}")
            continue
        findings.append(Finding(
            file=rel,
            line=int(line) if isinstance(line, int) else None,
            rule_id=str(rule_id),
            severity=map_severity("semgrep", str(native)),
            message=str(message).splitlines()[0] if message else str(rule_id),
            tool="semgrep",
        ))
    return findings, warnings, error_count


def run_semgrep(worktree_dir: Path, project_root: Path, *, timeout: int = 120) -> ScanResult:
    """Run Semgrep over ``worktree_dir`` and return a :class:`ScanResult`.

    ``project_root`` is where ``.semgrep.yml`` is discovered; ``worktree_dir`` is
    the scanned directory. A missing binary skips cleanly (FR-8); a timeout is a
    partial-results warning (NFR-1).
    """
    worktree_dir = Path(worktree_dir)
    project_root = Path(project_root)
    if not tool_available("semgrep"):
        return ScanResult(warnings=["SAST skipped: semgrep not installed"], skipped=True)

    config, warnings = discover_semgrep_config(project_root)
    cmd = ["semgrep", "--json", "--quiet", "--max-target-bytes", _MAX_TARGET_BYTES]
    if config is not None:
        cmd += ["--config", str(config)]
    else:
        cmd += ["--config", "p/default"]
    cmd.append(str(worktree_dir))

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        warnings.append(f"PARTIAL SCAN: semgrep timed out at {timeout}s — findings may be incomplete")
        return ScanResult(warnings=warnings)
    except OSError as exc:
        # Binary vanished between the availability check and exec, or a spawn
        # fault — treat as a skip rather than crashing the gate.
        logger.warning("semgrep invocation failed: %s", exc)
        return ScanResult(warnings=[f"SAST skipped: semgrep could not be executed ({exc})"], skipped=True)

    # Exit-code disambiguation (NFR-3, fail closed): 0 = clean, 1 = findings
    # present; anything else (2 = fatal: bad ruleset, offline p/default fetch,
    # internal crash) is an invocation error, not a clean scan.
    if proc.returncode not in (0, 1):
        detail = (proc.stderr or proc.stdout or "").strip()[:200]
        warnings.append(f"SAST INVOCATION-ERROR: semgrep exited {proc.returncode}: {detail}")
        return ScanResult(warnings=warnings, invocation_error=True)

    findings, parse_warnings, error_count = _parse_semgrep_json(proc.stdout, worktree_dir)
    warnings.extend(parse_warnings)
    if error_count:
        # Semgrep surfaces rule/config failures in its `errors` array even on an
        # exit-1 path; a populated array means the scan is not trustworthy.
        warnings.append(
            f"SAST INVOCATION-ERROR: semgrep reported {error_count} rule/config error(s) — scan may be incomplete"
        )
        return ScanResult(findings=findings, warnings=warnings, invocation_error=True)
    return ScanResult(findings=findings, warnings=warnings)
