"""SAST-local data model for the security gate (ticket 0025).

Kept separate from :mod:`models` because SAST findings carry ``rule_id`` and a
tiered ``severity`` enum that the lint/typecheck :class:`models.GateError` shape
does not have. If a harness-wide severity vocabulary is later introduced, migrate
:class:`Severity` here.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Severity(enum.Enum):
    """Harness severity vocabulary for a SAST finding.

    Ordered most-severe first. ``BLOCKER`` fails the gate; ``MAJOR`` and
    ``MINOR`` are surfaced as warnings that do not fail the gate.
    """

    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


#: Semgrep's native ``extra.severity`` field (ERROR/WARNING/INFO) → harness tier.
_SEMGREP_MAP: dict[str, Severity] = {
    "ERROR": Severity.BLOCKER,
    "WARNING": Severity.MAJOR,
    "INFO": Severity.MINOR,
}

#: Bandit's native ``issue_severity`` field (HIGH/MEDIUM/LOW) → harness tier.
_BANDIT_MAP: dict[str, Severity] = {
    "HIGH": Severity.BLOCKER,
    "MEDIUM": Severity.MAJOR,
    "LOW": Severity.MINOR,
}

#: tool name → its native-severity lookup table.
_TOOL_MAPS: dict[str, dict[str, Severity]] = {
    "semgrep": _SEMGREP_MAP,
    "bandit": _BANDIT_MAP,
}


def map_severity(tool: str, native: str) -> Severity:
    """Normalise a tool's native severity string to the harness :class:`Severity`.

    Case-insensitive. An unrecognised tool or native value degrades to
    ``Severity.MINOR`` rather than raising — an unknown severity must never be
    silently promoted to a gate-failing BLOCKER, and must never crash the scan.
    """
    table = _TOOL_MAPS.get(tool.lower(), {})
    return table.get((native or "").strip().upper(), Severity.MINOR)


@dataclass(frozen=True)
class Finding:
    """A single normalised SAST finding.

    ``file`` is relative to the scanned worktree; ``line`` is 1-indexed or
    ``None`` when the tool did not report one; ``rule_id`` is the tool's rule /
    check identifier; ``tool`` is the originating adapter (``"semgrep"`` /
    ``"bandit"``).
    """

    file: str
    line: int | None
    rule_id: str
    severity: Severity
    message: str
    tool: str


@dataclass
class ScanResult:
    """The outcome of one tool adapter run.

    ``findings`` are normalised results; ``warnings`` are non-fatal operator
    notes destined for ``gate-findings.md`` (floating ruleset, partial scan,
    out-of-tree path, invocation error); ``skipped`` is ``True`` when the tool
    was not installed or did not apply (e.g. no Python files for Bandit);
    ``invocation_error`` is ``True`` when the tool ran but failed in a way that
    must fail the gate closed (NFR-3).
    """

    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False
    invocation_error: bool = False
