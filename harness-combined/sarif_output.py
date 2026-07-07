"""Convert gate results to SARIF 2.1.0 and write them atomically.

SARIF (Static Analysis Results Interchange Format) is the JSON schema that VS
Code's Problems panel, GitHub Code Scanning, and multi-tool CI dashboards read.
This module is the *emission* half of ticket 0037: it maps the harness's own
``list[GateResult]`` onto a SARIF document and writes it to disk so those tools
can ingest gate findings without transcription.

The module is named ``sarif_output`` rather than ``sarif`` on purpose: the
``sarif-tools`` dev/test dependency installs an importable top-level ``sarif``
package, and a same-named local module would shadow it (or, once installed, be
shadowed by it) depending on ``sys.path`` order — a fragile, environment-dependent
binding. Keeping our module under a distinct name removes that hazard entirely.

Design constraints (see ``.tickets/0037-*/solution.md``):

* **Stdlib only.** ``json`` / ``pathlib`` / ``os`` / ``tempfile`` — zero new
  runtime dependencies; SARIF is plain JSON.
* **Deterministic.** No timestamps or UUIDs, so a re-run over unchanged findings
  produces a byte-identical file (clean CI diffs).
* **Trust boundary.** File URIs are POSIX-relative to ``worktree_root`` and are
  emitted only when the resolved path is *contained* within it — an absolute CI
  runner path must never leak into a SARIF file uploaded to an external service.
* **Non-fatal writes.** :func:`write_sarif` catches ``OSError`` and returns
  ``False`` rather than raising, so SARIF emission can never fail a gate run.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import TypedDict

from models import GateError, GateResult

logger = logging.getLogger(__name__)

#: The `_standards.md` opt-in line. Matched case-sensitively on the value so the
#: YAML-style lowercase ``true`` enables emission while the Python-capitalized
#: ``True`` / ``yes`` / ``on`` deliberately do NOT (FR-2 — no accidental enable
#: from a differently-spelled truthy token). Whitespace around the tokens is
#: flexible; ``re.MULTILINE`` lets the key appear on any line of the file.
_OPTIN_RE = re.compile(r"^\s*sarif_output\s*:\s*true\s*$", re.MULTILINE)

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
    "Schemata/sarif-schema-2.1.0.json"
)

#: ``GateError.severity`` (a raw, tool-dependent string) -> SARIF ``level``.
#: Keys are matched case-insensitively after stripping; an unknown severity
#: maps to ``warning`` (fail-safe — never silently drop a finding's visibility).
#: bandit's LOW is intentionally a ``note`` (annotation, not an actionable
#: warning) to avoid inflating IDE warning counts.
_SEVERITY_MAP: dict[str, str] = {
    "error": "error",
    "warning": "warning",
    "warn": "warning",
    "note": "note",
    "info": "note",
    "information": "note",
    "low": "note",
    "medium": "warning",
    "high": "error",
}


# ── SARIF document shape (structural, mypy-checkable) ─────────────────────────


class _ArtifactLocation(TypedDict):
    uri: str


class _Region(TypedDict):
    startLine: int


class _PhysicalLocation(TypedDict, total=False):
    artifactLocation: _ArtifactLocation
    region: _Region


class _Location(TypedDict):
    physicalLocation: _PhysicalLocation


class _Message(TypedDict):
    text: str


class _Result(TypedDict, total=False):
    ruleId: str
    level: str
    message: _Message
    locations: list[_Location]


class _Driver(TypedDict):
    name: str


class _Tool(TypedDict):
    driver: _Driver


class _Run(TypedDict):
    tool: _Tool
    results: list[_Result]


# ``$schema`` is not a valid Python identifier, so the document type uses the
# functional TypedDict syntax.
SarifDocument = TypedDict(
    "SarifDocument",
    {"$schema": str, "version": str, "runs": list[_Run]},
)


def _map_level(severity: str) -> str:
    """Map a raw ``GateError.severity`` string to a SARIF ``level``."""
    return _SEVERITY_MAP.get(severity.strip().lower(), "warning")


def _build_location(err: GateError, worktree_root: str) -> _Location | None:
    """Build a contained, POSIX-relative SARIF location, or ``None``.

    Returns ``None`` — meaning the result carries no ``physicalLocation`` — when
    the error has no file, or when the resolved file escapes ``worktree_root``.
    Never emits an absolute path or a ``file://`` URI.
    """
    if err.file is None:
        return None
    root = Path(worktree_root).resolve()
    candidate = Path(err.file)
    # A tool-relative path must anchor to the worktree, NOT the server cwd:
    # ``Path(file).resolve()`` alone would anchor to cwd and leak the wrong root.
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        return None
    physical: _PhysicalLocation = {
        "artifactLocation": {"uri": resolved.relative_to(root).as_posix()},
    }
    if err.line is not None:
        physical["region"] = {"startLine": err.line}
    return {"physicalLocation": physical}


def _build_result(err: GateError, worktree_root: str) -> _Result:
    """Map one ``GateError`` to a SARIF result.

    ``ruleId`` is omitted entirely when ``err.code`` is ``None`` (SARIF 2.1.0
    makes it optional). ``locations`` is omitted when the error has no contained
    file location.
    """
    result: _Result = {
        "level": _map_level(err.severity),
        "message": {"text": err.message},
    }
    if err.code is not None:
        result["ruleId"] = err.code
    location = _build_location(err, worktree_root)
    if location is not None:
        result["locations"] = [location]
    return result


def build_sarif(results: list[GateResult], worktree_root: str) -> SarifDocument:
    """Convert gate results to a SARIF 2.1.0 document.

    One SARIF ``run`` is emitted per distinct gate tool that produced at least
    one finding, with ``tool.driver.name`` set to ``GateResult.gate``. Gates that
    ran clean contribute no run (SARIF with an empty ``runs`` array is valid).
    """
    runs_by_gate: dict[str, _Run] = {}
    order: list[str] = []
    for gate_result in results:
        if not gate_result.errors:
            continue
        run = runs_by_gate.get(gate_result.gate)
        if run is None:
            run = {"tool": {"driver": {"name": gate_result.gate}}, "results": []}
            runs_by_gate[gate_result.gate] = run
            order.append(gate_result.gate)
        for err in gate_result.errors:
            run["results"].append(_build_result(err, worktree_root))
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [runs_by_gate[gate] for gate in order],
    }


def write_sarif(doc: SarifDocument, out_path: Path) -> bool:
    """Atomically write ``doc`` to ``out_path``; return success.

    Writes to a temp file in ``out_path.parent`` (same filesystem, so the final
    ``os.replace`` is atomic and never triggers a cross-device ``EXDEV``) and
    creates the parent directory first. Any ``OSError`` is logged and swallowed —
    a SARIF write failure must never fail the gate run — and ``False`` is
    returned so the caller can surface a ``sarif_write_failed`` signal.
    """
    out_path = Path(out_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(doc, indent=2)
        fd, tmp_name = tempfile.mkstemp(
            dir=out_path.parent, prefix=".results-", suffix=".sarif.tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, out_path)
        except OSError:
            # Best-effort cleanup of the orphaned temp file before failing.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return True
    except OSError as exc:
        logger.warning("Failed to write SARIF to %s: %s", out_path, exc)
        return False


def sarif_optin_enabled(project_root: str) -> bool:
    """True iff the harness-root ``_standards.md`` opts into SARIF emission.

    Enforces FR-2's trust boundary *in code*: only
    ``<project_root>/.tickets/_standards.md`` — the harness operator's config — is
    consulted. The path is constructed here from ``project_root`` alone, so a
    ``_standards.md`` inside a *scanned worktree* is structurally unreachable
    through this function and can never enable emission of the project's own
    findings. Fails closed (returns ``False``) when the file is absent or
    unreadable, and matches only the exact lowercase ``sarif_output: true``.
    """
    standards = Path(project_root) / ".tickets" / "_standards.md"
    try:
        text = standards.read_text(encoding="utf-8")
    except OSError:
        return False
    return _OPTIN_RE.search(text) is not None
