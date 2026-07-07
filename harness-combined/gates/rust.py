from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gates import (
    GateTimeoutConfig,
    ProcessResult,
    _timeout_error,
    run_dir_gates_scheduled,
    tool_skipped,
)
from gates._scope import GateSpec, has_scope_match
from models import GateError, GateResult

try:  # tomllib is stdlib on Python >= 3.11; tomli is the 3.10 backport
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python < 3.11
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]

# Tools this gate invokes via subprocess (see gates/python.py REQUIRED_TOOLS for
# the doctor contract). Every name must appear in a subprocess argument list.
REQUIRED_TOOLS: list[str] = ["cargo", "clippy"]

# Current stable Rust edition for generated code. Raised from 2021 to 2024 (stable
# since Rust 1.85, Feb 2025) so code using 2024-edition semantics compiles. Review
# cadence: revisit each January against the current Rust stable edition; a host
# Cargo.toml's edition overrides this (see host_rust_edition).
RUST_EDITION = "2024"


def _cargo_toml(edition: str) -> str:
    """Render the temp-crate Cargo.toml for a given edition."""
    return f"""\
[package]
name = "harness-temp"
version = "0.1.0"
edition = "{edition}"

[lib]
name = "harness_temp"
path = "src/lib.rs"

[dev-dependencies]
"""


def host_rust_edition(project_root: str | Path) -> str | None:
    """``[package].edition`` from a host ``Cargo.toml``, or None when unavailable.

    Text mode prefers this over ``RUST_EDITION`` so generated code compiles against
    the host project's declared edition (FR-5). A missing, unreadable, or malformed
    Cargo.toml — or one without a ``[package].edition`` — returns None.
    """
    try:
        with open(Path(project_root) / "Cargo.toml", "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    pkg = data.get("package")
    edition = pkg.get("edition") if isinstance(pkg, dict) else None
    return edition if isinstance(edition, str) and edition else None


_CARGO_TOML = _cargo_toml(RUST_EDITION)


@dataclass
class RustEnv:
    root: Path
    lib_file: Path


def _make_env(implementation: str, tests: str, project_root: str) -> RustEnv:
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_rs_"))
    (tmpdir / "Cargo.toml").write_text(
        _cargo_toml(host_rust_edition(project_root) or RUST_EDITION)
    )
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

def _check_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("typecheck", 120) if config else 120
    try:
        result = _exec(["cargo", "check", "--message-format=json", "--quiet"], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("check", timeout)
    errors = _parse_cargo_json(result.stdout)
    return GateResult(gate="check", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _clippy_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("lint", 120) if config else 120
    try:
        result = _exec(
            ["cargo", "clippy", "--message-format=json", "--quiet", "--", "-D", "warnings"],
            cwd, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _timeout_error("clippy", timeout)
    errors = _parse_cargo_json(result.stdout)
    return GateResult(gate="clippy", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _test_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("test", 180) if config else 180
    try:
        result = _exec(["cargo", "test", "--", "--nocapture"], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
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


def _audit_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    import shutil as _shutil
    if not _shutil.which("cargo-audit"):
        # Absent optional tool: warn-and-pass, never a silent pass (ticket 0043).
        return tool_skipped("audit", "cargo-audit", "cargo install cargo-audit")
    start = time.monotonic()
    timeout = config.timeout_for("security", 120) if config else 120
    try:
        result = _exec(["cargo", "audit", "--json"], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("audit", timeout)
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

def run_rust_suite(
    implementation: str, tests: str, project_root: str,
    config: GateTimeoutConfig | None = None,
) -> list[GateResult]:
    """Text mode: check → clippy → test → audit (temp dir)."""
    env = _make_env(implementation, tests, project_root)
    results = []
    try:
        for gate_fn in [_check_gate, _clippy_gate, _test_gate, _audit_gate]:
            result = gate_fn(env.root, config)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    return results


# ── Directory mode suite ──────────────────────────────────────────────────────

#: Source globs that make the Rust suite relevant.
_RUST_SCOPE = ["*.rs", "Cargo.toml", "Cargo.lock"]


def run_rust_suite_on_dir(
    directory: str, fail_fast: bool = True,
    config: GateTimeoutConfig | None = None,
    overrides: dict[str, list[str]] | None = None,
    changed_files: list[str] | None = None,
    max_workers: int | None = None,
    log_dir: Path | None = None,
) -> list[GateResult]:
    """Directory mode: check / clippy / test via ``GateScheduler``.

    ``check`` and ``clippy`` run concurrently; ``test`` waits on ``check`` per
    :data:`RUST_GATE_GRAPH`. ``max_workers=None`` (default) is auto: concurrent when
    ``fail_fast`` is False, sequential when True. An ``overrides`` entry replaces
    that gate's default command. When ``changed_files`` is supplied, a gate whose
    scope patterns do not overlap it is skipped — a passing ``skipped=True`` result
    (ticket 0030).
    """
    from gates.gate_graph import RUST_GATE_GRAPH

    gate_defs: list[tuple[str, GateSpec]] = [
        ("check", GateSpec(_check_gate, _RUST_SCOPE)),
        ("clippy", GateSpec(_clippy_gate, _RUST_SCOPE)),
        ("test", GateSpec(_test_gate, _RUST_SCOPE)),
    ]
    return run_dir_gates_scheduled(
        gate_defs, RUST_GATE_GRAPH, directory, log_namespace="rust",
        scope_check=has_scope_match,
        fail_fast=fail_fast, config=config, overrides=overrides,
        changed_files=changed_files, max_workers=max_workers, log_dir=log_dir,
    )
