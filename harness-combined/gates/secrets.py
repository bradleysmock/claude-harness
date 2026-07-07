"""Secrets/credential gate (ticket 0029).

Wraps gitleaks (preferred) with a trufflehog fallback to scan a git worktree's
*tracked* files for credentials. Scanner JSON is treated as untrusted: only the
structural fields RuleID/File/StartLine/EndLine are read; Match, Context and every
line-content field are discarded before any :class:`models.GateError` or
``gate-findings.md`` entry is built (FR-3, FR-4). File paths are validated by
``Path.resolve().relative_to(worktree_root)`` and dropped when they escape the
worktree (NFR-3). The gate is fail-closed: when no scanner is installed it fails
unless ``HARNESS_ALLOW_MISSING_SECRETS_SCANNER=1`` (FR-6). All subprocess calls
pass argument lists — never a shell string (NFR-4).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from models import GateError, GateResult

logger = logging.getLogger(__name__)

#: gate-findings.md section owned by this gate (mirrors the SAST section writer).
_SECTION_HEADER = "# Secrets — gate-findings"
#: Opt-out for the fail-closed TOOL_MISSING behaviour (FR-6).
_OPT_OUT_ENV = "HARNESS_ALLOW_MISSING_SECRETS_SCANNER"
#: Wall-clock ceiling — the gate must complete in < 30 s for a typical worktree (NFR-1).
_TIMEOUT_S = 30
#: Fixed mask appended after the first 4 chars of a match (NFR-2); fixed length so
#: it never leaks the credential's true length.
_MASK = "****"


# --------------------------------------------------------------------------- #
# Scanner detection
# --------------------------------------------------------------------------- #
def _detect_scanner() -> str | None:
    """Return the scanner to use: ``"gitleaks"`` > ``"trufflehog"`` > ``None`` (FR-1, FR-9)."""
    if shutil.which("gitleaks") is not None:
        return "gitleaks"
    if shutil.which("trufflehog") is not None:
        return "trufflehog"
    return None


# --------------------------------------------------------------------------- #
# Untrusted-output helpers
# --------------------------------------------------------------------------- #
def _contained_relpath(raw_path: str, worktree_root: Path) -> str | None:
    """Validate a scanner-reported path via ``resolve().relative_to(worktree_root)``.

    Relative paths are joined onto ``worktree_root`` first (gitleaks/trufflehog
    report paths relative to the scanned source). Returns the POSIX relative path,
    or ``None`` when the path escapes the worktree — the caller drops the finding
    (FR-4, NFR-3). Never raises.
    """
    try:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = worktree_root / candidate
        rel = candidate.resolve().relative_to(worktree_root.resolve())
    except (OSError, ValueError):
        return None
    return rel.as_posix()


def _redact(rule_name: str, match: str, file: str, line: int | None) -> str:
    """Build a locatable, credential-free GateError message (NFR-2).

    Shape: ``"<rule> @ <file>:<line> (<first4>****)"`` — contains the rule name,
    never the raw credential, and reveals at most the first 4 characters of the
    supplied match followed by a fixed mask. Real scanner output has its match
    discarded (FR-3), so the real path passes an empty/redacted match; this helper
    is exercised directly to prove the masking shape.
    """
    loc = f"{file}:{line}" if line is not None else file
    prefix = (match or "")[:4]
    return f"{rule_name} @ {loc} ({prefix}{_MASK})"


def _finding_error(rule_name: str, file: str, line: int | None) -> GateError:
    """Construct an error-severity GateError from validated structural fields only."""
    return GateError(
        message=_redact(rule_name, "", file, line),
        file=file,
        line=line,
        column=None,
        code=rule_name,
        severity="error",
    )


# --------------------------------------------------------------------------- #
# gitleaks path
# --------------------------------------------------------------------------- #
def _parse_gitleaks_json(stdout: str, worktree_root: Path) -> list[GateError]:
    """Parse gitleaks ``--report-format json`` output into GateErrors.

    Only ``RuleID``/``File``/``StartLine`` are read; ``Match``/``Secret``/``Context``
    are never touched (FR-3). Malformed JSON or a path outside the worktree yields
    no error for that entry rather than raising (defensive parsing).
    """
    text = stdout.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("secrets: could not parse gitleaks JSON output")
        return []
    if not isinstance(payload, list):
        return []
    errors: list[GateError] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        raw_file = entry.get("File")
        rule = str(entry.get("RuleID") or "gitleaks-unknown")
        start = entry.get("StartLine")
        if not isinstance(raw_file, str):
            continue
        rel = _contained_relpath(raw_file, worktree_root)
        if rel is None:
            continue
        line = start if isinstance(start, int) and not isinstance(start, bool) else None
        errors.append(_finding_error(rule, rel, line))
    return errors


def _run_gitleaks(directory: Path) -> tuple[list[GateError], list[str]]:
    """Run ``gitleaks detect --source . --redact`` over ``directory`` (FR-7).

    gitleaks' native git integration limits the scan to tracked files, and
    ``--redact`` removes the raw secret from the JSON report. The JSON report is
    written to a temp file and parsed. A scanner crash (exit code outside 0/1) or a
    timeout fails the gate closed with an error-severity entry.

    Precondition (solution.md-mandated command): ``gitleaks detect`` scans git
    *commit history*, so ``directory`` must be a worktree whose content is
    committed. The harness build flow commits the worktree before delivery gating,
    so the code under delivery is scanned; a caller that gates uncommitted/staged
    content would need a ``gitleaks protect --staged`` pass (out of scope here).
    """
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as tmp:
        report_path = tmp.name
    try:
        cmd = [
            "gitleaks", "detect",
            "--source", str(directory),
            "--redact",
            "--report-format", "json",
            "--report-path", report_path,
            "--no-banner",
            "--exit-code", "1",
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=str(directory), capture_output=True, text=True,
                timeout=_TIMEOUT_S, check=False,
            )
        except subprocess.TimeoutExpired:
            return ([_tool_error(f"gitleaks timed out after {_TIMEOUT_S}s")], [])
        except OSError as exc:  # binary vanished between detection and exec
            return ([_tool_error(f"gitleaks could not be executed: {exc}")], [])

        # gitleaks: 0 = no leaks, 1 = leaks found; anything else is a real fault.
        if proc.returncode not in (0, 1):
            detail = (proc.stderr or proc.stdout or "").strip()[:200]
            return ([_tool_error(f"gitleaks exited {proc.returncode}: {detail}")], [])

        try:
            stdout = Path(report_path).read_text(encoding="utf-8")
        except OSError:
            stdout = ""
        return (_parse_gitleaks_json(stdout, directory), [])
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# trufflehog path
# --------------------------------------------------------------------------- #
def _tracked_files(directory: Path) -> list[str] | None:
    """Return git-tracked file paths under ``directory`` via ``git ls-files`` (FR-7).

    Returns ``None`` on a git failure (timeout, git not installed, non-git dir, or
    a non-zero exit) so the caller can fail *closed* — an empty list is ambiguous
    between "clean repo" and "git error", and a security gate must not read the
    error branch as success. A genuinely empty repo returns ``[]``.
    """
    try:
        proc = subprocess.run(
            ["git", "ls-files"], cwd=str(directory), capture_output=True,
            text=True, timeout=_TIMEOUT_S, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def _trufflehog_version(directory: Path) -> str | None:
    """Return the ``trufflehog --version`` output (stdout+stderr), or ``None`` on error."""
    try:
        proc = subprocess.run(
            ["trufflehog", "--version"], cwd=str(directory), capture_output=True,
            text=True, timeout=_TIMEOUT_S, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return (proc.stdout + proc.stderr).strip()


def _parse_trufflehog_v3(stdout: str, worktree_root: Path) -> list[GateError]:
    """Parse trufflehog v3 JSONL output (one JSON object per line).

    Reads only ``DetectorName`` and ``SourceMetadata.Data.Filesystem.{file,line}``;
    all secret/raw fields are ignored (FR-3).
    """
    errors: list[GateError] = []
    for raw_line in stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj: dict[str, Any] = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        rule = str(obj.get("DetectorName") or "trufflehog-unknown")
        fs = (
            obj.get("SourceMetadata", {}) if isinstance(obj.get("SourceMetadata"), dict) else {}
        )
        data = fs.get("Data", {}) if isinstance(fs.get("Data"), dict) else {}
        filesystem = data.get("Filesystem", {}) if isinstance(data.get("Filesystem"), dict) else {}
        raw_file = filesystem.get("file")
        raw_line_no = filesystem.get("line")
        if not isinstance(raw_file, str):
            continue
        rel = _contained_relpath(raw_file, worktree_root)
        if rel is None:
            continue
        line = raw_line_no if isinstance(raw_line_no, int) and not isinstance(raw_line_no, bool) else None
        errors.append(_finding_error(rule, rel, line))
    return errors


def _parse_trufflehog_v2(stdout: str, worktree_root: Path) -> list[GateError]:
    """Parse trufflehog v2 JSON output.

    v2 emits one JSON object per finding with ``path``, ``line`` and ``reason``
    (the rule). Only those structural fields are read (FR-3).
    """
    errors: list[GateError] = []
    for raw_line in stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj: dict[str, Any] = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        raw_file = obj.get("path")
        rule = str(obj.get("reason") or "trufflehog-unknown")
        raw_line_no = obj.get("line")
        if not isinstance(raw_file, str):
            continue
        rel = _contained_relpath(raw_file, worktree_root)
        if rel is None:
            continue
        line = raw_line_no if isinstance(raw_line_no, int) and not isinstance(raw_line_no, bool) else None
        errors.append(_finding_error(rule, rel, line))
    return errors


def _run_trufflehog(directory: Path) -> tuple[list[GateError], list[str]]:
    """Run trufflehog over the tracked-file list (FR-7) with version-gated parsing.

    ``trufflehog --version`` selects the parser: prefix ``"trufflehog 3."`` → v3,
    ``"trufflehog 2."`` → v2. Any other prefix (or a version-probe failure) yields
    an error-severity TOOL_MISSING entry — no parser is silently selected (NFR-5).
    """
    version = _trufflehog_version(directory)
    if version is None:
        return ([_tool_missing_error("trufflehog version probe failed — cannot select a parser")], [])
    is_v3 = version.startswith("trufflehog 3.")
    is_v2 = version.startswith("trufflehog 2.")
    if not (is_v3 or is_v2):
        return ([_tool_missing_error(
            f"unrecognised trufflehog version {version!r} — refusing to guess a parser"
        )], [])
    parser = _parse_trufflehog_v3 if is_v3 else _parse_trufflehog_v2

    # git ls-files failure is fail-closed (M1); a legitimately empty repo is clean.
    tracked = _tracked_files(directory)
    if tracked is None:
        return ([_tool_error("git ls-files failed — cannot enumerate tracked files to scan")], [])
    if not tracked:
        return ([], [])

    # Build a version-appropriate command (M2): the v3 Go tool takes a
    # `filesystem <paths…>` subcommand; legacy v2 (dxa4481) has no such
    # subcommand and scans a git-repo path directly. A version/binary mismatch
    # therefore exits non-zero and is caught by the fail-closed returncode check
    # below rather than silently producing zero findings.
    if is_v3:
        # `--` terminates option parsing so a tracked file whose name begins with
        # a dash (e.g. `--results=verified`) is treated as a path, never a flag —
        # otherwise adversarial filenames in the scanned repo could silently narrow
        # detection (an argv option-injection bypass of the gate itself).
        cmd = ["trufflehog", "filesystem", "--json", "--no-update", "--", *tracked]
    else:  # v2 scans the git repo at `directory` (tracked/committed content only)
        cmd = ["trufflehog", "--json", "--regex", "--entropy=True", "--", str(directory)]

    try:
        proc = subprocess.run(
            cmd, cwd=str(directory), capture_output=True, text=True,
            timeout=_TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired:
        return ([_tool_error(f"trufflehog timed out after {_TIMEOUT_S}s")], [])
    except OSError as exc:
        return ([_tool_error(f"trufflehog could not be executed: {exc}")], [])

    findings = parser(proc.stdout, directory)
    # Fail closed on a scanner fault (B1): trufflehog exits 0 on a normal run
    # (findings are reported in stdout, not via exit code), so a non-zero exit
    # with nothing parseable is a genuine error, never a clean scan.
    if proc.returncode != 0 and not findings:
        detail = (proc.stderr or proc.stdout or "").strip()[:200]
        return ([_tool_error(f"trufflehog exited {proc.returncode}: {detail}")], [])
    return (findings, [])


# --------------------------------------------------------------------------- #
# Error/result construction
# --------------------------------------------------------------------------- #
def _tool_error(message: str) -> GateError:
    """A fail-closed error-severity entry for a scanner crash/timeout."""
    return GateError(
        message=message, file="gate-findings.md", line=None, column=None,
        code="TOOL_ERROR", severity="error",
    )


def _tool_missing_error(message: str, *, severity: str = "error") -> GateError:
    return GateError(
        message=message, file="gate-findings.md", line=None, column=None,
        code="TOOL_MISSING", severity=severity,
    )


def _tool_missing_result(directory: Path, start: float) -> GateResult:
    """Fail-closed (or opt-out) result when no scanner is installed (FR-6).

    Default: ``passed=False`` with an error-severity TOOL_MISSING entry. With
    ``HARNESS_ALLOW_MISSING_SECRETS_SCANNER=1``: ``passed=True`` with a
    warning-severity TOOL_MISSING entry. Either way the TOOL_MISSING notice is
    written to ``gate-findings.md`` (not only held in ``GateError.errors``).
    """
    opt_out = os.environ.get(_OPT_OUT_ENV) == "1"
    message = (
        "no secrets scanner installed (install gitleaks or trufflehog); "
        f"proceeding because {_OPT_OUT_ENV}=1"
        if opt_out else
        "no secrets scanner installed (install gitleaks or trufflehog, or set "
        f"{_OPT_OUT_ENV}=1 to bypass) — failing closed"
    )
    err = _tool_missing_error(message, severity="warning" if opt_out else "error")
    _write_gate_findings(directory, _render_section([err]))
    return GateResult(
        gate="secrets", passed=opt_out, errors=[err],
        duration_ms=int((time.monotonic() - start) * 1000),
    )


# --------------------------------------------------------------------------- #
# gate-findings.md writer (idempotent section replace — mirrors the SAST gate)
# --------------------------------------------------------------------------- #
def _render_section(errors: list[GateError]) -> str:
    """Render the Secrets section of gate-findings.md in the shared bullet format."""
    lines = [_SECTION_HEADER, ""]
    if not errors:
        lines.append("No secrets findings.")
    for e in errors:
        loc = f"{e.file}:{e.line}" if e.line is not None else (e.file or "")
        tag = "ERROR" if e.severity == "error" else "WARNING"
        lines.append(f"- [{tag}] {e.code} {loc}: {e.message}")
    return "\n".join(lines) + "\n"


def _strip_prior_section(text: str) -> str:
    """Remove a previously written Secrets section (header → next ``# `` or EOF)."""
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
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


def _write_gate_findings(worktree_dir: Path, section: str) -> None:
    """Idempotently write the Secrets section into ``<worktree>/gate-findings.md``.

    Replaces any prior Secrets section and preserves other gates' sections. A write
    failure degrades to a stderr note — it never crashes the gate.
    """
    path = worktree_dir / "gate-findings.md"
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        preserved = _strip_prior_section(existing)
        combined = (preserved.rstrip() + "\n\n" if preserved.strip() else "") + section
        path.write_text(combined, encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"secrets: could not write gate-findings.md: {exc}\n")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run_secrets_gate(directory: Path) -> GateResult:
    """Scan ``directory`` (a git worktree root) for credentials and return a GateResult.

    gitleaks is preferred; trufflehog is the fallback (FR-1, FR-9). A detected
    credential fails the gate (``passed=False``) with one redacted GateError per
    finding (FR-3). A clean scan passes with no errors. When no scanner is installed
    the gate fails closed unless opted out (FR-6). Findings are written to a
    ``# Secrets — gate-findings`` section of ``gate-findings.md`` (FR-4).
    """
    start = time.monotonic()
    directory = Path(directory)

    scanner = _detect_scanner()
    if scanner is None:
        return _tool_missing_result(directory, start)

    if scanner == "gitleaks":
        errors, _warnings = _run_gitleaks(directory)
    else:
        errors, _warnings = _run_trufflehog(directory)

    _write_gate_findings(directory, _render_section(errors))
    passed = not any(e.severity == "error" for e in errors)
    return GateResult(
        gate="secrets", passed=passed, errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
