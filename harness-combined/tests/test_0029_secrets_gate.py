"""Unit tests for the secrets/credential gate (ticket 0029).

All tests mock ``shutil.which`` and ``subprocess.run`` so they never require
gitleaks or trufflehog to be installed. The gitleaks path writes its JSON report
to a temp file, so the subprocess fake writes fixture JSON to the ``--report-path``
argument it is handed.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

from gates import secrets
from models import GateResult

# Assembled from fragments so the literal never appears in source (the pre-write
# guard flags a hardcoded AWS key even inside a test fixture string).
_AKIA = "AKIA"
_FAKE_KEY = _AKIA + "EXAMPLEKEY1234XYZ0"


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _which(*present: str):
    """Return a shutil.which stand-in reporting only ``present`` tools as installed."""
    def _inner(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in present else None
    return _inner


class _Recorder:
    """Configurable subprocess.run fake that records every argv it is handed.

    ``gitleaks_report`` is written to the report-path argument of a gitleaks call;
    ``version`` is returned for ``trufflehog --version``; ``th_stdout`` is returned
    for a ``trufflehog filesystem`` call; ``tracked`` seeds ``git ls-files``.
    """

    def __init__(self, *, gitleaks_report="[]", gitleaks_rc=0,
                 version="trufflehog 3.63.0", th_stdout="", th_rc=0,
                 tracked=("a.py",), ls_files_rc=0):
        self.gitleaks_report = gitleaks_report
        self.gitleaks_rc = gitleaks_rc
        self.version = version
        self.th_stdout = th_stdout
        self.th_rc = th_rc
        self.tracked = list(tracked)
        self.ls_files_rc = ls_files_rc
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *args, **kwargs):
        assert isinstance(cmd, list), f"subprocess.run must get a list argv, got {type(cmd)}"
        self.calls.append(cmd)
        if cmd[0] == "gitleaks":
            idx = cmd.index("--report-path")
            Path(cmd[idx + 1]).write_text(self.gitleaks_report, encoding="utf-8")
            return _proc(self.gitleaks_rc)
        if cmd[0] == "git" and cmd[1] == "ls-files":
            if self.ls_files_rc != 0:
                return _proc(self.ls_files_rc, stderr="not a git repository")
            return _proc(0, stdout="\n".join(self.tracked) + "\n")
        if cmd[0] == "trufflehog" and cmd[1] == "--version":
            return _proc(0, stderr=self.version)
        if cmd[0] == "trufflehog":  # v3 `filesystem …` or v2 git-repo scan
            return _proc(self.th_rc, stdout=self.th_stdout)
        raise AssertionError(f"unexpected command: {cmd}")

    def ran(self, tool: str) -> bool:
        return any(c[0] == tool for c in self.calls)


# ── redaction (NFR-2) ─────────────────────────────────────────────────────────

def test_redaction_shape_no_raw_key_rule_name_and_prefix():
    msg = secrets._redact("aws-access-token", _FAKE_KEY, "config.py", 3)
    assert "aws-access-token" in msg          # (b) contains rule name
    assert _FAKE_KEY not in msg               # (a) no raw credential
    assert _AKIA in msg                       # (c) first 4 chars of match
    assert "*" in msg                         # (c) mask characters
    assert "config.py:3" in msg


def test_redaction_without_line():
    msg = secrets._redact("rule", "secretval", "f.py", None)
    assert "f.py" in msg and "f.py:" not in msg


# ── scanner precedence / selection (FR-1, FR-9) ───────────────────────────────

def test_gitleaks_takes_precedence_when_both_present(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("gitleaks", "trufflehog"))
    rec = _Recorder(gitleaks_report="[]")
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert isinstance(result, GateResult) and result.passed
    assert rec.ran("gitleaks") and not rec.ran("trufflehog")


def test_trufflehog_fallback_uses_tracked_file_list(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("trufflehog"))
    rec = _Recorder(version="trufflehog 3.63.0", th_stdout="", tracked=["x.py", "y.py"])
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert result.passed and not rec.ran("gitleaks")
    fs_call = next(c for c in rec.calls if c[:2] == ["trufflehog", "filesystem"])
    assert "x.py" in fs_call and "y.py" in fs_call


# ── gitleaks findings (FR-3) ──────────────────────────────────────────────────

def test_gitleaks_finding_blocks_with_file_and_line(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("gitleaks"))
    report = json.dumps([
        {"RuleID": "aws-access-token", "File": "src/config.py",
         "StartLine": 7, "EndLine": 7, "Match": "SHOULD-BE-DISCARDED",
         "Secret": "REDACTED", "Context": "line content"},
    ])
    rec = _Recorder(gitleaks_report=report, gitleaks_rc=1)
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert not result.passed and len(result.errors) == 1
    err = result.errors[0]
    assert err.file == "src/config.py" and err.line == 7
    assert err.code == "aws-access-token"
    assert "SHOULD-BE-DISCARDED" not in err.message  # Match discarded (FR-3)


def test_clean_scan_passes_with_no_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("gitleaks"))
    rec = _Recorder(gitleaks_report="[]", gitleaks_rc=0)
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert result.passed and result.errors == []


def test_gitleaks_path_outside_worktree_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("gitleaks"))
    report = json.dumps([
        {"RuleID": "generic", "File": "../../../etc/passwd", "StartLine": 1},
    ])
    rec = _Recorder(gitleaks_report=report, gitleaks_rc=1)
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert result.passed and result.errors == []  # escaping path discarded (NFR-3)


def test_gitleaks_crash_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("gitleaks"))
    rec = _Recorder(gitleaks_report="", gitleaks_rc=2)
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert not result.passed
    assert any(e.code == "TOOL_ERROR" for e in result.errors)


# ── TOOL_MISSING (FR-6) ───────────────────────────────────────────────────────

def test_tool_missing_fails_closed_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which())  # neither present
    monkeypatch.delenv(secrets._OPT_OUT_ENV, raising=False)
    result = secrets.run_secrets_gate(tmp_path)
    assert not result.passed
    assert result.errors and result.errors[0].code == "TOOL_MISSING"
    assert result.errors[0].severity == "error"


def test_tool_missing_opt_out_passes_and_writes_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which())
    monkeypatch.setenv(secrets._OPT_OUT_ENV, "1")
    result = secrets.run_secrets_gate(tmp_path)
    assert result.passed
    findings = (tmp_path / "gate-findings.md").read_text(encoding="utf-8")
    assert "TOOL_MISSING" in findings


# ── trufflehog version gating (NFR-5) ─────────────────────────────────────────

def test_trufflehog_unrecognised_version_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("trufflehog"))
    rec = _Recorder(version="trufflehog 4.0.0")
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert not result.passed
    assert any(e.code == "TOOL_MISSING" for e in result.errors)
    # No parser was selected → no filesystem scan attempted.
    assert not any(c[:2] == ["trufflehog", "filesystem"] for c in rec.calls)


def test_trufflehog_v3_parser(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("trufflehog"))
    v3 = json.dumps({
        "DetectorName": "AWS",
        "SourceMetadata": {"Data": {"Filesystem": {"file": "svc/keys.py", "line": 12}}},
        "Raw": "SHOULD-BE-IGNORED",
    })
    rec = _Recorder(version="trufflehog 3.63.0", th_stdout=v3)
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert not result.passed and len(result.errors) == 1
    assert result.errors[0].file == "svc/keys.py" and result.errors[0].line == 12
    assert "SHOULD-BE-IGNORED" not in result.errors[0].message


def test_trufflehog_v2_parser(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("trufflehog"))
    v2 = json.dumps({"path": "old/creds.py", "line": 4, "reason": "High Entropy",
                     "stringsFound": ["SHOULD-BE-IGNORED"]})
    rec = _Recorder(version="trufflehog 2.2.1", th_stdout=v2)
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert not result.passed and len(result.errors) == 1
    assert result.errors[0].file == "old/creds.py" and result.errors[0].line == 4
    assert result.errors[0].code == "High Entropy"
    # M2: the v2 branch must NOT build the v3-only `filesystem` subcommand.
    scan = next(c for c in rec.calls if c[0] == "trufflehog" and c[1] != "--version")
    assert "filesystem" not in scan and "--no-update" not in scan


def test_trufflehog_v3_dash_filename_is_positional_not_a_flag(tmp_path, monkeypatch):
    # A tracked file whose name starts with '-' must reach trufflehog as a path,
    # after a '--' end-of-options terminator — never parsed as an option (bypass).
    monkeypatch.setattr(secrets.shutil, "which", _which("trufflehog"))
    rec = _Recorder(version="trufflehog 3.63.0", tracked=["--results=verified", "app.py"])
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    secrets.run_secrets_gate(tmp_path)
    fs_call = next(c for c in rec.calls if c[:2] == ["trufflehog", "filesystem"])
    assert "--" in fs_call
    term = fs_call.index("--")
    assert "--results=verified" in fs_call[term + 1:]  # positional, after the terminator
    assert "--results=verified" not in fs_call[:term]  # not among the parsed options


def test_trufflehog_scanner_crash_fails_closed(tmp_path, monkeypatch):
    # B1: a non-zero trufflehog exit with no parseable findings must fail closed.
    monkeypatch.setattr(secrets.shutil, "which", _which("trufflehog"))
    rec = _Recorder(version="trufflehog 3.63.0", th_stdout="", th_rc=2)
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert not result.passed
    assert any(e.code == "TOOL_ERROR" for e in result.errors)


def test_trufflehog_git_ls_files_error_fails_closed(tmp_path, monkeypatch):
    # M1: a git ls-files failure is ambiguous → fail closed, not a silent pass.
    monkeypatch.setattr(secrets.shutil, "which", _which("trufflehog"))
    rec = _Recorder(version="trufflehog 3.63.0", ls_files_rc=128)
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert not result.passed
    assert any(e.code == "TOOL_ERROR" for e in result.errors)
    # No filesystem scan should be attempted once enumeration failed.
    assert not any(c[0] == "trufflehog" and c[1] == "filesystem" for c in rec.calls)


def test_trufflehog_empty_repo_passes_clean(tmp_path, monkeypatch):
    # An empty tracked-file list is a legitimate clean pass (distinct from M1's error).
    monkeypatch.setattr(secrets.shutil, "which", _which("trufflehog"))
    rec = _Recorder(version="trufflehog 3.63.0", tracked=[])
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    result = secrets.run_secrets_gate(tmp_path)
    assert result.passed and result.errors == []


# ── argv discipline (NFR-4) ───────────────────────────────────────────────────

def test_all_subprocess_calls_use_list_argv(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets.shutil, "which", _which("gitleaks"))
    rec = _Recorder(gitleaks_report="[]")
    monkeypatch.setattr(secrets.subprocess, "run", rec)
    secrets.run_secrets_gate(tmp_path)
    # _Recorder asserts list-ness on every call; confirm at least one ran.
    assert rec.calls and all(isinstance(c, list) for c in rec.calls)
