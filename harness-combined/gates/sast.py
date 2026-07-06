"""SAST gate orchestrator (ticket 0025).

Runs the Semgrep and Bandit adapters, aggregates their findings, applies the
BLOCKER threshold, writes a ``# SAST — gate-findings`` section to
``gate-findings.md`` in the existing bullet format (FR-5/FR-9), and returns a
:class:`models.GateResult`. HIGH → BLOCKER fails the gate; MEDIUM/LOW → warnings
that do not fail it (FR-3/FR-4/FR-6). When both tools are unavailable the gate
passes with a single "SAST skipped" warning (FR-8). A tool invocation error
fails the gate closed (NFR-3).
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from gates.sast_bandit import run_bandit
from gates.sast_models import Finding, ScanResult, Severity
from gates.sast_semgrep import run_semgrep
from models import GateError, GateResult

logger = logging.getLogger(__name__)

_SECTION_HEADER = "# SAST — gate-findings"


def _finding_to_gate_error(finding: Finding) -> GateError:
    """Adapt a SAST :class:`Finding` to the shared :class:`models.GateError`.

    BLOCKER → ``"error"`` (fails the gate); MAJOR/MINOR → ``"warning"``.
    """
    return GateError(
        message=f"{finding.rule_id}: {finding.message}",
        file=finding.file,
        line=finding.line,
        column=None,
        code=finding.rule_id,
        severity="error" if finding.severity is Severity.BLOCKER else "warning",
    )


def _warning_to_gate_error(warning: str) -> GateError:
    return GateError(
        message=warning, file="gate-findings.md", line=None, column=None,
        code="SAST_WARNING", severity="warning",
    )


def _render_section(findings: list[Finding], warnings: list[str]) -> str:
    """Render the SAST gate-findings.md section in the shared bullet format."""
    lines = [_SECTION_HEADER, ""]
    if not findings and not warnings:
        lines.append("No SAST findings.")
    for w in warnings:
        # Warning strings already carry their own 'SAST ...' prefix; don't double it.
        lines.append(f"- [WARNING] {w}")
    for f in sorted(findings, key=lambda x: (x.severity.value, x.file, x.line or 0)):
        loc = f"{f.file}:{f.line}" if f.line is not None else f.file
        lines.append(f"- [{f.severity.value}] {f.rule_id} {loc}: {f.message}")
    return "\n".join(lines) + "\n"


def _write_gate_findings(worktree_dir: Path, section: str) -> None:
    """Idempotently write the SAST section into ``<worktree_dir>/gate-findings.md``.

    Replaces any prior SAST section and preserves other gates' sections (append
    otherwise). A write failure degrades to a stderr note — it never crashes the
    gate.
    """
    path = worktree_dir / "gate-findings.md"
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        preserved = _strip_prior_section(existing)
        combined = (preserved.rstrip() + "\n\n" if preserved.strip() else "") + section
        path.write_text(combined, encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"sast: could not write gate-findings.md: {exc}\n")


def _strip_prior_section(text: str) -> str:
    """Remove a previously written SAST section from gate-findings.md text.

    A section runs from its ``# SAST — gate-findings`` header to the next
    top-level ``# `` header or end of file.
    """
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith(_SECTION_HEADER):
            skipping = True
            continue
        if skipping:
            if line.startswith("# ") and not line.startswith(_SECTION_HEADER):
                skipping = False
            else:
                continue
        out.append(line)
    return "\n".join(out)


def run_sast_gate(worktree_dir: str | Path, project_root: str | Path, *, timeout: int = 120) -> GateResult:
    """Run the SAST gate over ``worktree_dir`` and return a :class:`GateResult`.

    ``project_root`` is where ``.semgrep.yml`` / ``bandit.ini`` are discovered;
    in directory mode the scanned worktree owns its own configs so the two are
    usually the same path.
    """
    start = time.monotonic()
    worktree_dir = Path(worktree_dir)
    project_root = Path(project_root)

    results: list[ScanResult] = [
        run_semgrep(worktree_dir, project_root, timeout=timeout),
        run_bandit(worktree_dir, project_root, timeout=timeout),
    ]
    findings = [f for r in results for f in r.findings]
    warnings = [w for r in results for w in r.warnings]
    invocation_error = any(r.invocation_error for r in results)

    if all(r.skipped for r in results) and not findings:
        # Neither tool ran — a clean, non-failing skip (FR-8). Collapse the
        # per-tool skip notes into one operator-facing warning.
        warnings = ["SAST skipped due to missing tooling — install semgrep and/or bandit to enable"]

    has_blocker = any(f.severity is Severity.BLOCKER for f in findings)
    passed = not has_blocker and not invocation_error

    section = _render_section(findings, warnings)
    _write_gate_findings(worktree_dir, section)

    errors = [_finding_to_gate_error(f) for f in findings]
    errors += [_warning_to_gate_error(w) for w in warnings]
    if invocation_error and not has_blocker:
        # Ensure a failing gate always carries at least one error-severity entry
        # so it can never report passed=False with an empty/all-warning errors
        # list (mirrors the no-silent-failure invariant of the other gates).
        errors.append(GateError(
            message="SAST tool invocation error — gate failed closed",
            file="gate-findings.md", line=None, column=None,
            code="SAST_INVOCATION_ERROR", severity="error",
        ))

    return GateResult(
        gate="sast", passed=passed, errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
