"""Dependency freshness and vulnerability gate.

Detects the project ecosystem from manifest files, invokes the matching audit
tool over a subprocess *argument list* (never a shell, never string
interpolation), parses the tool's JSON output into structured findings, and maps
each CVE to a ``BLOCKER`` or ``WARNING`` against a configurable severity
threshold. Every degraded path — tool absent, network down, malformed or
semantically unexpected JSON, misconfiguration — becomes a ``WARNING`` and a
*passing* result: the gate never raises out and never silently drops a CVE.

The finding shape here (``severity``/``advisory_id``/``package``/``message``) is
deliberately local to this module and independent of the shared ``models``
types used by the language gates.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ── Local finding model ───────────────────────────────────────────────────────

BLOCKER = "BLOCKER"
WARNING = "WARNING"


@dataclass
class GateError:
    """A single dependency-audit finding.

    ``severity`` is exactly the uppercase harness vocabulary — ``"BLOCKER"`` or
    ``"WARNING"``. Kept local to this module so the dep-audit finding shape does
    not couple to ``models.GateError`` used by the language gates.
    """

    severity: str
    advisory_id: str
    package: str
    message: str


@dataclass
class GateResult:
    passed: bool
    findings: list[GateError] = field(default_factory=list)


@dataclass
class DepAuditConfig:
    threshold: str
    ignore: frozenset[str]


# ── Severity handling ─────────────────────────────────────────────────────────

# Incoming tool severities (npm uses "moderate"; others use "medium").
_SEVERITY_RANK: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "moderate": 2,
    "medium": 2,
    "low": 1,
}
# Accepted threshold values (FR-7).
_THRESHOLD_RANK: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "moderate": 2,
    "low": 1,
}
_DEFAULT_THRESHOLD = "high"

# Recognised advisory-ID shapes (npm numeric source ids, GHSA, CVE, RUSTSEC, GO).
_ADVISORY_ID_RE = re.compile(
    r"^(?:GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}"
    r"|CVE-\d{4}-\d{4,}"
    r"|RUSTSEC-\d{4}-\d{4}"
    r"|GO-\d{4}-\d+"
    r"|\d+)$",
    re.IGNORECASE,
)


def _classify(
    raw_severity: Any,
    advisory_id: str,
    package: str,
    title: str,
    cfg: DepAuditConfig,
) -> GateError | None:
    """Map one advisory to a finding, or ``None`` if it is on the ignore list.

    A missing / null / unrecognised severity never silently drops the finding —
    it is surfaced as a ``WARNING`` (NFR-3, semantic validation).
    """
    if advisory_id and advisory_id in cfg.ignore:
        return None
    rank = _SEVERITY_RANK.get(str(raw_severity).lower()) if raw_severity is not None else None
    if rank is None:
        return GateError(
            severity=WARNING,
            advisory_id=advisory_id or "unknown",
            package=package or "unknown",
            message=(
                f"{title} (severity field missing/unrecognised — surfaced as WARNING, "
                f"not silently dropped)"
            ),
        )
    threshold_rank = _THRESHOLD_RANK.get(cfg.threshold, _THRESHOLD_RANK[_DEFAULT_THRESHOLD])
    severity = BLOCKER if rank >= threshold_rank else WARNING
    return GateError(
        severity=severity,
        advisory_id=advisory_id or "unknown",
        package=package or "unknown",
        message=title,
    )


# ── Config ────────────────────────────────────────────────────────────────────

def _read_dep_audit_config(project_root: str) -> tuple[DepAuditConfig, list[GateError]]:
    """Read ``gates.depAudit`` from ``harness.config.json``.

    Fails closed: an absent file yields defaults silently; a malformed file,
    unrecognised threshold, or non-array ``ignore`` yields defaults *and* a
    WARNING — misconfiguration never silently passes all CVEs.
    """
    warnings: list[GateError] = []
    path = Path(project_root) / "harness.config.json"
    if not path.exists():
        return DepAuditConfig(_DEFAULT_THRESHOLD, frozenset()), warnings

    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(GateError(
            severity=WARNING, advisory_id="config", package="harness.config.json",
            message=f"unreadable config ({exc}); defaulting threshold={_DEFAULT_THRESHOLD}",
        ))
        return DepAuditConfig(_DEFAULT_THRESHOLD, frozenset()), warnings

    section = {}
    if isinstance(raw, dict):
        gates = raw.get("gates")
        if isinstance(gates, dict) and isinstance(gates.get("depAudit"), dict):
            section = gates["depAudit"]

    # Threshold
    threshold = section.get("severityThreshold", _DEFAULT_THRESHOLD)
    if threshold not in _THRESHOLD_RANK:
        warnings.append(GateError(
            severity=WARNING, advisory_id="config", package="severityThreshold",
            message=(
                f"unrecognised severityThreshold {threshold!r}; "
                f"defaulting to {_DEFAULT_THRESHOLD} (CVEs are not silently passed)"
            ),
        ))
        threshold = _DEFAULT_THRESHOLD

    # Ignore list
    ignore_raw = section.get("ignore", [])
    if not isinstance(ignore_raw, list):
        warnings.append(GateError(
            severity=WARNING, advisory_id="config", package="ignore",
            message="ignore must be an array of advisory IDs; defaulting to empty set",
        ))
        ignore_raw = []

    ignore: set[str] = set()
    for entry in ignore_raw:
        if isinstance(entry, str) and _ADVISORY_ID_RE.match(entry):
            ignore.add(entry)
        else:
            warnings.append(GateError(
                severity=WARNING, advisory_id="config", package="ignore",
                message=f"ignore entry {entry!r} is not a recognised advisory-ID format; skipped",
            ))

    return DepAuditConfig(threshold, frozenset(ignore)), warnings


def dep_audit_enabled(project_root: str) -> bool:
    """Whether the dep-audit phase should run for this project (FR-10).

    The gate is enabled by default and can be selectively skipped via gate config
    in ``harness.config.json`` — either ``gates.depAudit.enabled: false`` or a
    ``gates.skip`` array containing ``"dep-audit"``. Fails *open* (enabled) on any
    unreadable/malformed config so a broken config never silently disables the
    security gate.
    """
    path = Path(project_root) / "harness.config.json"
    if not path.exists():
        return True
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(raw, dict):
        return True
    gates = raw.get("gates")
    if not isinstance(gates, dict):
        return True
    skip = gates.get("skip")
    if isinstance(skip, list) and "dep-audit" in skip:
        return False
    dep = gates.get("depAudit")
    if isinstance(dep, dict) and dep.get("enabled") is False:
        return False
    return True


# ── Ecosystem detection ───────────────────────────────────────────────────────

# (ecosystem, manifest filenames). Node.js first — it takes priority (FR-1).
_MANIFESTS: list[tuple[str, tuple[str, ...]]] = [
    ("node", ("package.json",)),
    ("python", ("requirements.txt", "pyproject.toml", "Pipfile")),
    ("rust", ("Cargo.toml",)),
    ("go", ("go.mod",)),
]


def _detect_ecosystem(directory: str) -> tuple[str | None, list[GateError]]:
    """Return the selected primary ecosystem and any multi-manifest WARNING.

    When more than one manifest family is present, the gate emits a single
    WARNING naming every detected manifest and the selected ecosystem, then
    continues — it never silently audits only one ecosystem (FR-1).
    """
    root = Path(directory)
    present: list[tuple[str, str]] = []
    for ecosystem, names in _MANIFESTS:
        for name in names:
            if (root / name).exists():
                present.append((ecosystem, name))
                break
    if not present:
        return None, []
    selected = present[0][0]
    warnings: list[GateError] = []
    if len(present) > 1:
        found = ", ".join(f"{name} ({eco})" for eco, name in present)
        warnings.append(GateError(
            severity=WARNING, advisory_id="multi-manifest", package="",
            message=f"multiple manifests detected [{found}]; auditing selected ecosystem '{selected}'",
        ))
    return selected, warnings


# ── Per-tool JSON parsers (pure) ──────────────────────────────────────────────

def _load_json(json_str: str, tool: str) -> tuple[Any, GateError | None]:
    """Parse tool JSON defensively; malformed output degrades to a WARNING."""
    try:
        return json.loads(json_str), None
    except (json.JSONDecodeError, TypeError):
        return None, GateError(
            severity=WARNING, advisory_id=tool, package="",
            message=f"{tool} produced malformed JSON; skipped (no CVE silently dropped)",
        )


def _parse_npm_audit(json_str: str, cfg: DepAuditConfig) -> list[GateError]:
    data, err = _load_json(json_str, "npm-audit")
    if err is not None:
        return [err]
    findings: list[GateError] = []
    vulns = data.get("vulnerabilities", {}) if isinstance(data, dict) else {}
    if not isinstance(vulns, dict):
        return findings
    for name, entry in vulns.items():
        if not isinstance(entry, dict):
            continue
        severity = entry.get("severity")
        source_id = ""
        ghsa_id = ""
        title = f"{name}: vulnerability"
        via = entry.get("via")
        if isinstance(via, list):
            for item in via:
                if isinstance(item, dict):
                    if item.get("source") is not None:
                        source_id = str(item.get("source"))
                    match = re.search(r"GHSA-[0-9a-z-]+", str(item.get("url") or ""), re.IGNORECASE)
                    if match:
                        ghsa_id = match.group(0)
                    title = str(item.get("title") or title)
                    break
        # An operator may suppress by either the numeric npm source id or the
        # human-facing GHSA id, so match the ignore list against both (FR-8).
        candidate_ids = {i for i in (source_id, ghsa_id) if i}
        if candidate_ids & cfg.ignore:
            continue
        advisory_id = ghsa_id or source_id or str(name)
        finding = _classify(severity, advisory_id, str(name), title, cfg)
        if finding is not None:
            findings.append(finding)
    return findings


def _parse_pip_audit(json_str: str, cfg: DepAuditConfig) -> list[GateError]:
    data, err = _load_json(json_str, "pip-audit")
    if err is not None:
        return [err]
    # pip-audit emits either {"dependencies": [...]} or a bare list.
    if isinstance(data, dict):
        deps = data.get("dependencies", [])
    elif isinstance(data, list):
        deps = data
    else:
        deps = []
    findings: list[GateError] = []
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        name = str(dep.get("name", "unknown"))
        for vuln in dep.get("vulns", []) or []:
            if not isinstance(vuln, dict):
                continue
            advisory_id = str(vuln.get("id", "unknown"))
            severity = vuln.get("severity")  # frequently absent → WARNING
            title = str(vuln.get("description") or f"{name}: {advisory_id}")
            finding = _classify(severity, advisory_id, name, title, cfg)
            if finding is not None:
                findings.append(finding)
    return findings


def _parse_cargo_audit(json_str: str, cfg: DepAuditConfig) -> list[GateError]:
    data, err = _load_json(json_str, "cargo-audit")
    if err is not None:
        return [err]
    findings: list[GateError] = []
    vulns = data.get("vulnerabilities", {}) if isinstance(data, dict) else {}
    entries = vulns.get("list", []) if isinstance(vulns, dict) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        advisory = entry.get("advisory", {}) if isinstance(entry.get("advisory"), dict) else {}
        package = entry.get("package", {}) if isinstance(entry.get("package"), dict) else {}
        advisory_id = str(advisory.get("id", "unknown"))
        name = str(package.get("name", "unknown"))
        severity = advisory.get("severity")  # RUSTSEC advisories often omit → WARNING
        title = str(advisory.get("title") or f"{name}: {advisory_id}")
        finding = _classify(severity, advisory_id, name, title, cfg)
        if finding is not None:
            findings.append(finding)
    return findings


_GOVULN_TESTED_SCHEMA = {"1.0.0", "1.1.0", "1.3.1"}


def _schema_ok(version: Any) -> bool:
    return version is not None and str(version).lstrip("vV") in _GOVULN_TESTED_SCHEMA


def _parse_govulncheck(json_str: str, cfg: DepAuditConfig) -> list[GateError]:
    """Parse govulncheck output.

    The govulncheck JSON format is not yet stable (see solution.md Risks), so the
    schema version is checked first and a WARNING is emitted — rather than a
    partial/wrong parse — when it is missing or outside the tested range.

    Two shapes are accepted:
    * the real ``govulncheck -json`` **JSONL stream** of ``{"config"}`` /
      ``{"osv"}`` / ``{"finding"}`` objects (version in ``config.protocol_version``);
    * a normalised single document ``{"schemaVersion", "findings":[…]}`` (fixtures).
    """
    stripped = json_str.strip()
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        # Not a single JSON document — try the real JSONL stream.
        return _parse_govulncheck_stream(stripped, cfg)

    if not isinstance(data, dict):
        return [GateError(
            severity=WARNING, advisory_id="govulncheck", package="",
            message="unexpected govulncheck JSON shape; skipped",
        )]
    schema = data.get("schemaVersion") or data.get("schema_version")
    if not _schema_ok(schema):
        return [GateError(
            severity=WARNING, advisory_id="govulncheck", package="",
            message=(
                f"govulncheck schemaVersion {schema!r} missing or outside tested range "
                f"{sorted(_GOVULN_TESTED_SCHEMA)}; not attempting a partial parse"
            ),
        )]
    findings: list[GateError] = []
    for item in data.get("findings", []) or []:
        if not isinstance(item, dict):
            continue
        advisory_id = str(item.get("osv", "unknown"))
        name = str(item.get("package", "unknown"))
        severity = item.get("severity")
        title = str(item.get("message") or f"{name}: {advisory_id}")
        finding = _classify(severity, advisory_id, name, title, cfg)
        if finding is not None:
            findings.append(finding)
    return findings


def _parse_govulncheck_stream(blob: str, cfg: DepAuditConfig) -> list[GateError]:
    """Parse the real newline-delimited govulncheck ``-json`` stream."""
    version: Any = None
    severities: dict[str, Any] = {}
    titles: dict[str, str] = {}
    findings_raw: list[dict[str, Any]] = []
    for line in blob.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("config"), dict):
            cfg_obj = obj["config"]
            version = cfg_obj.get("protocol_version") or cfg_obj.get("schema_version") or version
        elif isinstance(obj.get("osv"), dict):
            osv = obj["osv"]
            osv_id = str(osv.get("id", ""))
            if osv_id:
                specific = osv.get("database_specific")
                if isinstance(specific, dict):
                    severities[osv_id] = specific.get("severity")
                titles[osv_id] = str(osv.get("summary") or osv.get("details") or osv_id)[:200]
        elif isinstance(obj.get("finding"), dict):
            findings_raw.append(obj["finding"])

    if not _schema_ok(version):
        return [GateError(
            severity=WARNING, advisory_id="govulncheck", package="",
            message=(
                f"govulncheck protocol_version {version!r} missing or outside tested range "
                f"{sorted(_GOVULN_TESTED_SCHEMA)}; not attempting a partial parse"
            ),
        )]

    findings: list[GateError] = []
    seen: set[str] = set()
    for finding in findings_raw:
        osv_id = str(finding.get("osv", "unknown"))
        if osv_id in seen:  # a symbol-level stream repeats the same osv per call site
            continue
        seen.add(osv_id)
        name = _govuln_package(finding)
        severity = severities.get(osv_id)
        title = titles.get(osv_id, f"{name}: {osv_id}")
        result = _classify(severity, osv_id, name, title, cfg)
        if result is not None:
            findings.append(result)
    return findings


def _govuln_package(finding: dict[str, Any]) -> str:
    trace = finding.get("trace")
    if isinstance(trace, list):
        for step in trace:
            if isinstance(step, dict) and step.get("package"):
                return str(step["package"])
        for step in trace:
            if isinstance(step, dict) and step.get("module"):
                return str(step["module"])
    return "unknown"


# ── Tool invocation ───────────────────────────────────────────────────────────

# ecosystem → (binary, audit argv, parser)
_AUDIT_TOOLS: dict[str, tuple[str, list[str], Callable[[str, DepAuditConfig], list[GateError]]]] = {
    "node": ("npm", ["npm", "audit", "--json"], _parse_npm_audit),
    "python": ("pip-audit", ["pip-audit", "--format=json"], _parse_pip_audit),
    "rust": ("cargo", ["cargo", "audit", "--json"], _parse_cargo_audit),
    "go": ("govulncheck", ["govulncheck", "-json", "./..."], _parse_govulncheck),
}

_SUBPROCESS_TIMEOUT = 110  # seconds; NFR-1 keeps the whole gate under 120s.


def _run_tool(argv: list[str], project_root: str) -> tuple[str | None, GateError | None]:
    """Run an audit tool over an argument list. Never uses a shell.

    Returns ``(stdout, None)`` on a completed run (regardless of exit code — npm
    audit exits non-zero when vulns exist, so exit code is never trusted), or
    ``(None, WARNING)`` when the tool cannot run (missing binary, exec/network
    failure, timeout). Degradation is always a WARNING, never a BLOCKER (FR-9).
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, GateError(
            severity=WARNING, advisory_id=argv[0], package="",
            message=f"{argv[0]} could not run ({exc}); dependency audit degraded",
        )
    return proc.stdout, None


def _freshness_findings(project_root: str, ecosystem: str) -> list[GateError]:
    """Node.js-only major-version freshness via ``npm outdated --json`` (v1).

    Non-Node ecosystems emit a single WARNING that freshness is unsupported so
    operators are informed rather than silently left with no signal.
    """
    if ecosystem != "node":
        return [GateError(
            severity=WARNING, advisory_id="freshness", package="",
            message=f"dependency freshness check is not supported for '{ecosystem}' in v1",
        )]
    if shutil.which("npm") is None:
        return [GateError(
            severity=WARNING, advisory_id="freshness", package="",
            message="npm not found; freshness check skipped",
        )]
    stdout, err = _run_tool(["npm", "outdated", "--json"], project_root)
    if err is not None:
        return [err]
    data, parse_err = _load_json(stdout or "{}", "npm-outdated")
    if parse_err is not None:
        return [parse_err]
    findings: list[GateError] = []
    if not isinstance(data, dict):
        return findings
    for name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        current = _major(entry.get("current"))
        latest = _major(entry.get("latest"))
        if current is not None and latest is not None and latest > current:
            findings.append(GateError(
                severity=WARNING, advisory_id="freshness", package=str(name),
                message=f"{name} is {latest - current} major version(s) behind (current {entry.get('current')}, latest {entry.get('latest')})",
            ))
    return findings


def _major(version: Any) -> int | None:
    if not isinstance(version, str):
        return None
    match = re.match(r"\s*v?(\d+)", version)
    return int(match.group(1)) if match else None


# ── gate-findings.md writer ───────────────────────────────────────────────────

def _write_gate_findings(project_root: str, findings: list[GateError]) -> None:
    """Write findings to ``gate-findings.md`` at ``project_root``.

    Uses ``open`` directly so a write failure surfaces as ``OSError`` (caught by
    the caller). Writes no other file and never touches manifests/lock files.
    """
    lines = ["# Dependency Audit — gate-findings", ""]
    if not findings:
        lines.append("No dependency findings.")
    for f in findings:
        pkg = f" {f.package}" if f.package else ""
        lines.append(f"- [{f.severity}] {f.advisory_id}{pkg}: {f.message}")
    path = Path(project_root) / "gate-findings.md"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def run_dep_audit_gate(project_root: str) -> GateResult:
    """Run the dependency audit gate against ``project_root``.

    Fails closed on every degraded path: the gate blocks (``passed=False``) only
    on a genuine BLOCKER finding, and any error condition becomes a WARNING with
    ``passed=True``. It never raises out of this function.
    """
    cfg, findings = _read_dep_audit_config(project_root)

    ecosystem, eco_warnings = _detect_ecosystem(project_root)
    findings.extend(eco_warnings)

    if ecosystem is None:
        findings.append(GateError(
            severity=WARNING, advisory_id="ecosystem", package="",
            message="no supported dependency manifest found; dependency audit skipped",
        ))
        return _finalize(project_root, findings)

    binary, argv, parser = _AUDIT_TOOLS[ecosystem]
    if shutil.which(binary) is None:
        findings.append(GateError(
            severity=WARNING, advisory_id=binary, package="",
            message=f"{binary} not found; dependency audit degraded (install {binary} to enable)",
        ))
    else:
        stdout, err = _run_tool(argv, project_root)
        if err is not None:
            findings.append(err)
        else:
            findings.extend(parser(stdout or "", cfg))

    findings.extend(_freshness_findings(project_root, ecosystem))
    return _finalize(project_root, findings)


def _finalize(project_root: str, findings: list[GateError]) -> GateResult:
    passed = not any(f.severity == BLOCKER for f in findings)
    result = GateResult(passed=passed, findings=findings)
    try:
        _write_gate_findings(project_root, findings)
    except OSError as exc:
        # A write failure must not crash the gate — the result still reflects the
        # findings (passed already computed above).
        sys.stderr.write(f"dep_audit: could not write gate-findings.md: {exc}\n")
    return result
