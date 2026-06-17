from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gates import ProcessResult
from models import GateError, GateResult

_CARGO_TOML = """\
[package]
name = "harness-temp"
version = "0.1.0"
edition = "2021"

[lib]
name = "harness_temp"
path = "src/lib.rs"

[dev-dependencies]
"""


@dataclass
class RustEnv:
    root: Path
    lib_file: Path


def _make_env(implementation: str, tests: str, project_root: str) -> RustEnv:
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_rs_"))
    (tmpdir / "Cargo.toml").write_text(_CARGO_TOML)
    src = tmpdir / "src"
    src.mkdir()
    lib = src / "lib.rs"
    combined = implementation
    tests_stripped = tests.strip()
    if tests_stripped and tests_stripped not in combined:
        if "#[cfg(test)]" not in combined:
            combined += f"\n\n{tests_stripped}"
    lib.write_text(combined, encoding="utf-8")
    return RustEnv(root=tmpdir, lib_file=lib)


def _exec(command: list[str], cwd: str | Path, timeout: int = 120) -> ProcessResult:
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=str(cwd), timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _timeout_error(gate: str) -> GateResult:
    return GateResult(
        gate=gate, passed=False,
        errors=[GateError(message="Timed out", file=None, line=None, column=None,
                          code="TIMEOUT", severity="error")],
        duration_ms=120000,
    )


def _parse_cargo_json(stdout: str) -> list[GateError]:
    errors = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("reason") != "compiler-message":
            continue
        msg: dict[str, Any] = obj.get("message", {})
        level = msg.get("level", "")
        if level not in ("error", "warning"):
            continue
        spans: list[Any] = msg.get("spans", [])
        primary = next((s for s in spans if s.get("is_primary")), spans[0] if spans else None)
        errors.append(GateError(
            message=msg.get("message", ""),
            file=primary["file_name"] if primary else None,
            line=primary["line_start"] if primary else None,
            column=primary["column_start"] if primary else None,
            code=msg.get("code", {}).get("code") if msg.get("code") else None,
            severity=level,
        ))
    return errors


# ── Shared gate functions (work on any cwd) ───────────────────────────────────

def _check_gate(cwd: str | Path) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec(["cargo", "check", "--message-format=json", "--quiet"], cwd)
    except subprocess.TimeoutExpired:
        return _timeout_error("check")
    errors = _parse_cargo_json(result.stdout)
    return GateResult(gate="check", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _clippy_gate(cwd: str | Path) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec(
            ["cargo", "clippy", "--message-format=json", "--quiet", "--", "-D", "warnings"], cwd
        )
    except subprocess.TimeoutExpired:
        return _timeout_error("clippy")
    errors = _parse_cargo_json(result.stdout)
    return GateResult(gate="clippy", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _test_gate(cwd: str | Path) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec(["cargo", "test", "--", "--nocapture"], cwd, timeout=180)
    except subprocess.TimeoutExpired:
        return _timeout_error("test")
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors = []
    for line in result.output.splitlines():
        if "FAILED" in line and "test " in line:
            test_name = line.strip().split()[1] if len(line.split()) > 1 else line
            errors.append(GateError(
                message=f"Test failed: {test_name}",
                file=None, line=None, column=None,
                code="TEST_FAILURE", severity="error",
            ))
        elif "panicked at" in line and errors:
            last = errors[-1]
            errors[-1] = GateError(
                message=f"{last.message} — {line.strip()}",
                file=last.file, line=last.line, column=last.column,
                code=last.code, severity=last.severity,
            )
    if not errors:
        errors.append(GateError(
            message=result.output[:600], file=None,
            line=None, column=None, code="TEST_FAILURE", severity="error",
        ))
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def _audit_gate(cwd: str | Path) -> GateResult:
    import shutil as _shutil
    if not _shutil.which("cargo-audit"):
        return GateResult(gate="audit", passed=True, errors=[], duration_ms=0)
    start = time.monotonic()
    try:
        result = _exec(["cargo", "audit", "--json"], cwd)
    except subprocess.TimeoutExpired:
        return _timeout_error("audit")
    errors = []
    try:
        report: dict[str, Any] = json.loads(result.stdout)
        for vuln in report.get("vulnerabilities", {}).get("list", []):
            adv = vuln.get("advisory", {})
            pkg = vuln.get("package", {})
            errors.append(GateError(
                message=(f"{pkg.get('name', '?')} {pkg.get('version', '?')}: "
                         f"{adv.get('title', 'vulnerability')} ({adv.get('id', '')})"),
                file="Cargo.toml", line=None, column=None,
                code=adv.get("id"), severity="error",
            ))
    except json.JSONDecodeError:
        pass
    return GateResult(gate="audit", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


# ── Text mode suite ───────────────────────────────────────────────────────────

def run_rust_suite(implementation: str, tests: str, project_root: str) -> list[GateResult]:
    """Text mode: check → clippy → test → audit (temp dir)."""
    env = _make_env(implementation, tests, project_root)
    results = []
    try:
        for gate_fn in [_check_gate, _clippy_gate, _test_gate, _audit_gate]:
            result = gate_fn(env.root)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    return results


# ── Directory mode suite ──────────────────────────────────────────────────────

def run_rust_suite_on_dir(
    directory: str, fail_fast: bool = True
) -> list[GateResult]:
    """Directory mode: check → clippy → test (actual project dir, no audit)."""
    results = []
    for gate_fn in [_check_gate, _clippy_gate, _test_gate]:
        result = gate_fn(directory)
        results.append(result)
        if not result.passed and fail_fast:
            return results
    return results
