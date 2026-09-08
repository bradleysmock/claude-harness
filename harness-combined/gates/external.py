"""Pluggable external gates — SARIF-in (ticket 0077).

Lets `_standards.md` declare an `[external_gates]` entry naming an
already-installed subprocess whose stdout is SARIF 2.1.0, parsed into
`GateResult`/`GateError` by `run_external_gate` — no new `gates/*.py` module
required to add a SARIF-emitting tool. Scheduled and reported exactly like a
built-in gate: appended sequentially in `run_suite_on_dir`, never through the
`GateSpec`/scheduler path (see `gates/__init__.py`).
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gates import _timeout_error
from models import GateError, GateResult

#: Cap on SARIF `results` array size across all runs — an oversized array
#: from a misbehaving or hostile scanner must not balloon `gate-findings.md`.
MAX_SARIF_RESULTS = 500

#: SARIF `level` -> `GateError.severity`. Unrecognized levels degrade to
#: "warning" rather than raising.
_LEVEL_MAP = {"error": "error", "warning": "warning", "note": "warning"}


@dataclass(frozen=True)
class ExternalGateSpec:
    name: str
    command: list[str]
    scope: str | None
    timeout_seconds: int


def _resolve_contained_path(raw_path: str, directory: str) -> str | None:
    """Mirror `sarif_output.py`'s `_build_location`: an ingested path that is
    absolute or escapes `directory` becomes `None`, never passed through raw."""
    root = Path(directory).resolve()
    candidate = Path(raw_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        return None
    return resolved.relative_to(root).as_posix()


def _parse_sarif(stdout: str, directory: str) -> tuple[list[GateError], bool]:
    """Return `(errors, sarif_valid)`. `sarif_valid=False` means TOOL_ERROR
    territory: absent/malformed SARIF, or a `results` array over the cap."""
    if not stdout.strip():
        return [], False
    try:
        doc: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError:
        return [], False

    raw_results: list[dict[str, Any]] = []
    for run in doc.get("runs", []):
        raw_results.extend(run.get("results", []))
    if len(raw_results) > MAX_SARIF_RESULTS:
        return [], False

    errors: list[GateError] = []
    for result in raw_results:
        file_path = None
        line = None
        locations = result.get("locations") or []
        if locations:
            physical = locations[0].get("physicalLocation", {})
            uri = physical.get("artifactLocation", {}).get("uri")
            if uri:
                file_path = _resolve_contained_path(uri, directory)
            line = physical.get("region", {}).get("startLine")
        message = (result.get("message") or {}).get("text", "")
        errors.append(GateError(
            message=message, file=file_path, line=line, column=None,
            code=result.get("ruleId"),
            severity=_LEVEL_MAP.get(result.get("level", "warning"), "warning"),
        ))
    return errors, True


def run_external_gate(spec: ExternalGateSpec, directory: str) -> GateResult:
    """Run `spec.command` as an argv list (`shell=False`) against `directory`
    and parse its SARIF stdout. Non-zero exit alone is never sufficient for
    `TOOL_ERROR` — many scanners exit non-zero because they found something."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            spec.command, cwd=directory, capture_output=True, text=True,
            timeout=spec.timeout_seconds, shell=False,
        )
    except subprocess.TimeoutExpired:
        return _timeout_error(spec.name, spec.timeout_seconds)
    except OSError as exc:
        return GateResult(
            gate=spec.name, passed=False,
            errors=[GateError(
                message=f"failed to run {spec.command[0]!r}: {exc}",
                file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
            )],
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    errors, sarif_valid = _parse_sarif(result.stdout, directory)
    if not sarif_valid:
        fallback = (result.stdout or result.stderr or "no output on stdout")[:500]
        return GateResult(
            gate=spec.name, passed=False,
            errors=[GateError(
                message=fallback, file=None, line=None, column=None,
                code="TOOL_ERROR", severity="error",
            )],
            duration_ms=duration_ms,
        )
    return GateResult(gate=spec.name, passed=not errors, errors=errors, duration_ms=duration_ms)
