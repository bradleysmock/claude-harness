"""Unit + integration tests for the dependency audit gate (ticket 0012).

The subprocess boundary is the only external dependency, so every test mocks it
(``unittest.mock.patch``) — no live network calls, no live audit tools. Canned
tool JSON is defined as in-module constants and fed only as mocked stdout.
"""

from __future__ import annotations

import json
from unittest import mock

from gates.dep_audit import (
    _AUDIT_TOOLS,
    BLOCKER,
    WARNING,
    DepAuditConfig,
    GateError,
    GateResult,
    _detect_ecosystem,
    _parse_cargo_audit,
    _parse_govulncheck,
    _parse_npm_audit,
    _parse_pip_audit,
    _read_dep_audit_config,
    dep_audit_enabled,
    run_dep_audit_gate,
)

# ── Canned tool JSON (fixtures) ───────────────────────────────────────────────
# npm audit --json — captured shape from npm 10.x (auditReportVersion 2).
NPM_AUDIT_CVE = json.dumps({
    "vulnerabilities": {
        "lodash": {
            "name": "lodash",
            "severity": "high",
            "via": [{
                "source": 1065,
                "title": "Prototype Pollution in lodash",
                "url": "https://github.com/advisories/GHSA-p6mc-m468-83gw",
                "severity": "high",
            }],
            "range": "<4.17.21",
        }
    },
    "metadata": {},
})
NPM_AUDIT_CLEAN = json.dumps({"vulnerabilities": {}, "metadata": {}})
NPM_OUTDATED_STALE = json.dumps({
    "lodash": {"current": "3.10.1", "wanted": "3.10.1", "latest": "4.17.21"}
})
NPM_OUTDATED_EMPTY = "{}"

# pip-audit --format=json — pip-audit 2.x (no per-vuln severity field).
PIP_AUDIT_VULN = json.dumps({
    "dependencies": [
        {"name": "jinja2", "version": "2.11.2",
         "vulns": [{"id": "GHSA-g3rq-g295-4j3m", "description": "XSS", "fix_versions": ["2.11.3"]}]}
    ]
})

# cargo audit --json — cargo-audit 0.18.
CARGO_AUDIT_CVE = json.dumps({
    "vulnerabilities": {
        "found": True, "count": 1,
        "list": [{
            "advisory": {"id": "RUSTSEC-2021-0001", "title": "flaw", "severity": "critical"},
            "package": {"name": "smallvec", "version": "0.6.0"},
        }],
    }
})

# govulncheck -json — normalised fixture shape, schemaVersion 1.0.0.
GOVULN_OK = json.dumps({
    "schemaVersion": "1.0.0",
    "findings": [{"osv": "GO-2021-0001", "package": "golang.org/x/text", "severity": "high"}],
})
GOVULN_NO_SCHEMA = json.dumps({"findings": [{"osv": "GO-2021-0001", "package": "x", "severity": "high"}]})
# Real `govulncheck -json` output: a newline-delimited stream of separate objects.
GOVULN_STREAM = "\n".join([
    json.dumps({"config": {"protocol_version": "v1.0.0", "scanner_name": "govulncheck"}}),
    json.dumps({"progress": {"message": "Scanning your code..."}}),
    json.dumps({"osv": {"id": "GO-2021-0113", "summary": "Directory traversal",
                        "database_specific": {"severity": "HIGH"}}}),
    json.dumps({"finding": {"osv": "GO-2021-0113",
                           "trace": [{"module": "golang.org/x/net", "package": "golang.org/x/net/html"}]}}),
    # symbol-level streams repeat the same osv per call site — must de-dupe.
    json.dumps({"finding": {"osv": "GO-2021-0113",
                           "trace": [{"module": "golang.org/x/net", "package": "golang.org/x/net/html"}]}}),
])
GOVULN_STREAM_NO_CONFIG = json.dumps(
    {"finding": {"osv": "GO-2021-0113", "trace": [{"package": "x"}]}}
)

DEFAULT_CFG = DepAuditConfig("high", frozenset())


def _completed(stdout: str, returncode: int = 0):
    return mock.Mock(stdout=stdout, stderr="", returncode=returncode)


# ── FR-1: ecosystem detection ─────────────────────────────────────────────────

def test_detect_node_only(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    eco, warnings = _detect_ecosystem(str(tmp_path))
    assert eco == "node"
    assert warnings == []


def test_detect_multi_manifest_warns_and_selects_node(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "requirements.txt").write_text("")
    eco, warnings = _detect_ecosystem(str(tmp_path))
    assert eco == "node"  # Node.js takes priority
    assert len(warnings) == 1
    assert warnings[0].severity == WARNING
    assert "package.json" in warnings[0].message and "requirements.txt" in warnings[0].message


def test_detect_go_only(tmp_path):
    (tmp_path / "go.mod").write_text("module x")
    eco, warnings = _detect_ecosystem(str(tmp_path))
    assert eco == "go"
    assert warnings == []


def test_detect_none(tmp_path):
    eco, warnings = _detect_ecosystem(str(tmp_path))
    assert eco is None
    assert warnings == []


# ── FR-3 / FR-5 / FR-6: parsing, severity, block/pass ─────────────────────────

def test_npm_cve_maps_to_blocker():
    findings = _parse_npm_audit(NPM_AUDIT_CVE, DEFAULT_CFG)
    assert len(findings) == 1
    assert findings[0].severity == BLOCKER
    assert findings[0].package == "lodash"
    # GHSA id (what npm shows humans) is preferred over the opaque numeric source.
    assert findings[0].advisory_id == "GHSA-p6mc-m468-83gw"


def test_npm_clean_is_empty():
    assert _parse_npm_audit(NPM_AUDIT_CLEAN, DEFAULT_CFG) == []


def test_result_passed_false_on_blocker():
    r = GateResult(passed=False, findings=[GateError(BLOCKER, "x", "p", "m")])
    assert r.passed is False


def test_cargo_critical_is_blocker():
    findings = _parse_cargo_audit(CARGO_AUDIT_CVE, DEFAULT_CFG)
    assert findings and findings[0].severity == BLOCKER
    assert findings[0].advisory_id == "RUSTSEC-2021-0001"


# ── FR-7: threshold config ────────────────────────────────────────────────────

def test_threshold_critical_downgrades_high_to_warning():
    cfg = DepAuditConfig("critical", frozenset())
    findings = _parse_npm_audit(NPM_AUDIT_CVE, cfg)
    assert findings[0].severity == WARNING


def test_unrecognised_threshold_defaults_high_and_warns(tmp_path):
    (tmp_path / "harness.config.json").write_text(
        json.dumps({"gates": {"depAudit": {"severityThreshold": "bogus"}}})
    )
    cfg, warnings = _read_dep_audit_config(str(tmp_path))
    assert cfg.threshold == "high"
    assert any(w.package == "severityThreshold" for w in warnings)


# ── FR-8: ignore list ─────────────────────────────────────────────────────────

def test_ignore_drops_matching_advisory_by_source_id():
    cfg = DepAuditConfig("high", frozenset({"1065"}))
    assert _parse_npm_audit(NPM_AUDIT_CVE, cfg) == []


def test_ignore_drops_matching_advisory_by_ghsa():
    # Operators suppress by the GHSA id npm surfaces to humans (FR-8, MINOR-1 fix).
    cfg = DepAuditConfig("high", frozenset({"GHSA-p6mc-m468-83gw"}))
    assert _parse_npm_audit(NPM_AUDIT_CVE, cfg) == []


def test_ignore_non_id_format_warns(tmp_path):
    (tmp_path / "harness.config.json").write_text(
        json.dumps({"gates": {"depAudit": {"ignore": ["not an id!"]}}})
    )
    cfg, warnings = _read_dep_audit_config(str(tmp_path))
    assert cfg.ignore == frozenset()
    assert any(w.package == "ignore" for w in warnings)


def test_ignore_scalar_warns_and_empties(tmp_path):
    (tmp_path / "harness.config.json").write_text(
        json.dumps({"gates": {"depAudit": {"ignore": "GHSA-p6mc-m468-83gw"}}})
    )
    cfg, warnings = _read_dep_audit_config(str(tmp_path))
    assert cfg.ignore == frozenset()
    assert any(w.package == "ignore" for w in warnings)


# ── FR-9 / NFR-3: graceful degradation ────────────────────────────────────────

def test_missing_tool_warns_and_passes(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    with mock.patch("gates.dep_audit.shutil.which", return_value=None):
        result = run_dep_audit_gate(str(tmp_path))
    assert result.passed is True
    assert any(f.severity == WARNING for f in result.findings)


def test_malformed_json_warns_no_exception():
    findings = _parse_npm_audit("{not json", DEFAULT_CFG)
    assert len(findings) == 1
    assert findings[0].severity == WARNING


def test_null_severity_surfaces_warning():
    payload = json.dumps({"vulnerabilities": {
        "pkg": {"name": "pkg", "severity": None, "via": [{"source": 42, "title": "t"}]}
    }})
    findings = _parse_npm_audit(payload, DEFAULT_CFG)
    assert len(findings) == 1 and findings[0].severity == WARNING


def test_missing_severity_key_surfaces_warning():
    findings = _parse_pip_audit(PIP_AUDIT_VULN, DEFAULT_CFG)  # pip-audit omits severity
    assert len(findings) == 1 and findings[0].severity == WARNING
    assert findings[0].advisory_id == "GHSA-g3rq-g295-4j3m"


# ── govulncheck schema version ────────────────────────────────────────────────

def test_govulncheck_ok_schema_parses():
    findings = _parse_govulncheck(GOVULN_OK, DEFAULT_CFG)
    assert len(findings) == 1 and findings[0].severity == BLOCKER


def test_govulncheck_missing_schema_warns():
    findings = _parse_govulncheck(GOVULN_NO_SCHEMA, DEFAULT_CFG)
    assert len(findings) == 1 and findings[0].severity == WARNING
    assert "schemaVersion" in findings[0].message


def test_govulncheck_real_jsonl_stream_parses_and_dedupes():
    findings = _parse_govulncheck(GOVULN_STREAM, DEFAULT_CFG)
    assert len(findings) == 1  # de-duped across repeated symbol-level findings
    assert findings[0].severity == BLOCKER
    assert findings[0].advisory_id == "GO-2021-0113"
    assert findings[0].package == "golang.org/x/net/html"


def test_govulncheck_stream_without_config_version_warns():
    findings = _parse_govulncheck(GOVULN_STREAM_NO_CONFIG, DEFAULT_CFG)
    assert len(findings) == 1 and findings[0].severity == WARNING


# ── FR-2: tool selection ──────────────────────────────────────────────────────

def test_tool_selection_argv_per_ecosystem():
    assert _AUDIT_TOOLS["node"][1] == ["npm", "audit", "--json"]
    assert _AUDIT_TOOLS["python"][1] == ["pip-audit", "--format=json"]
    assert _AUDIT_TOOLS["rust"][1] == ["cargo", "audit", "--json"]
    assert _AUDIT_TOOLS["go"][1] == ["govulncheck", "-json", "./..."]


# ── Config edge cases ─────────────────────────────────────────────────────────

def test_config_absent_defaults_no_warning(tmp_path):
    cfg, warnings = _read_dep_audit_config(str(tmp_path))
    assert cfg.threshold == "high" and cfg.ignore == frozenset()
    assert warnings == []


def test_config_malformed_defaults_and_warns(tmp_path):
    (tmp_path / "harness.config.json").write_text("{not json")
    cfg, warnings = _read_dep_audit_config(str(tmp_path))
    assert cfg.threshold == "high"
    assert warnings and warnings[0].severity == WARNING


# ── FR-10: selective skip ─────────────────────────────────────────────────────

def test_dep_audit_enabled_by_default(tmp_path):
    assert dep_audit_enabled(str(tmp_path)) is True


def test_dep_audit_disabled_via_enabled_false(tmp_path):
    (tmp_path / "harness.config.json").write_text(
        json.dumps({"gates": {"depAudit": {"enabled": False}}})
    )
    assert dep_audit_enabled(str(tmp_path)) is False


def test_dep_audit_disabled_via_skip_list(tmp_path):
    (tmp_path / "harness.config.json").write_text(
        json.dumps({"gates": {"skip": ["dep-audit"]}})
    )
    assert dep_audit_enabled(str(tmp_path)) is False


def test_dep_audit_fails_open_on_malformed_config(tmp_path):
    (tmp_path / "harness.config.json").write_text("{not json")
    assert dep_audit_enabled(str(tmp_path)) is True  # broken config never disables the gate


# ── Integration: subprocess mocked ────────────────────────────────────────────

def test_integration_npm_blocker_writes_findings(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    with mock.patch("gates.dep_audit.shutil.which", return_value="/usr/bin/npm"), \
         mock.patch("gates.dep_audit.subprocess.run",
                    side_effect=[_completed(NPM_AUDIT_CVE, 1), _completed(NPM_OUTDATED_EMPTY, 0)]):
        result = run_dep_audit_gate(str(tmp_path))
    assert result.passed is False
    written = (tmp_path / "gate-findings.md").read_text()
    assert "BLOCKER" in written
    assert "lodash" in written
    assert "GHSA-p6mc-m468-83gw" in written


def test_integration_no_shell_kwarg(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    with mock.patch("gates.dep_audit.shutil.which", return_value="/usr/bin/npm"), \
         mock.patch("gates.dep_audit.subprocess.run",
                    side_effect=[_completed(NPM_AUDIT_CLEAN, 0), _completed(NPM_OUTDATED_STALE, 0)]) as run:
        run_dep_audit_gate(str(tmp_path))
    assert run.call_count == 2
    for call in run.call_args_list:
        assert call.kwargs.get("shell") in (None, False)
        assert isinstance(call.args[0], list)  # argument list, not a string


def test_integration_freshness_warning_for_stale_node(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    with mock.patch("gates.dep_audit.shutil.which", return_value="/usr/bin/npm"), \
         mock.patch("gates.dep_audit.subprocess.run",
                    side_effect=[_completed(NPM_AUDIT_CLEAN, 0), _completed(NPM_OUTDATED_STALE, 0)]):
        result = run_dep_audit_gate(str(tmp_path))
    assert result.passed is True
    assert any(f.advisory_id == "freshness" and "behind" in f.message for f in result.findings)


def test_integration_python_freshness_unsupported(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    with mock.patch("gates.dep_audit.shutil.which", return_value="/usr/bin/pip-audit"), \
         mock.patch("gates.dep_audit.subprocess.run",
                    side_effect=[_completed("[]", 0)]):
        result = run_dep_audit_gate(str(tmp_path))
    assert result.passed is True
    assert any("not supported for 'python'" in f.message for f in result.findings)


def test_gate_findings_write_failure_does_not_raise(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    with mock.patch("gates.dep_audit.shutil.which", return_value="/usr/bin/npm"), \
         mock.patch("gates.dep_audit.subprocess.run",
                    side_effect=[_completed(NPM_AUDIT_CVE, 1), _completed(NPM_OUTDATED_EMPTY, 0)]), \
         mock.patch("gates.dep_audit.open", create=True, side_effect=PermissionError("denied")):
        result = run_dep_audit_gate(str(tmp_path))
    assert isinstance(result, GateResult)
    assert result.passed is False  # BLOCKER still reflected despite write failure


def test_no_manifest_passes_with_warning(tmp_path):
    result = run_dep_audit_gate(str(tmp_path))
    assert result.passed is True
    assert any("no supported dependency manifest" in f.message for f in result.findings)
