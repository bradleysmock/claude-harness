from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gates import (
    GateTimeoutConfig,
    ProcessResult,
    _run_override_gate,
    _timeout_error,
    append_tool_error_if_silent,
)
from models import GateError, GateResult

# Tools this gate invokes via subprocess. Single source of truth consumed by
# gates/doctor.py to build its probe registry (ticket 0022). Every name here
# must appear in a subprocess argument list below; the doctor CI invariant test
# enforces that structurally (AST), so keep this in sync when tooling changes.
REQUIRED_TOOLS: list[str] = ["mypy", "ruff", "bandit"]


@dataclass
class ExecutionEnvironment:
    root: Path
    implementation_file: Path
    test_file: Path
    pythonpath: list[str]


def _make_env(implementation: str, tests: str, project_root: str) -> ExecutionEnvironment:
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_"))
    impl = tmpdir / "implementation.py"
    test_file = tmpdir / "test_implementation.py"
    impl.write_text(implementation, encoding="utf-8")
    test_file.write_text(
        f"import sys\n"
        f"sys.path.insert(0, '{tmpdir}')\n"
        f"sys.path.insert(0, '{project_root}')\n\n"
        + tests,
        encoding="utf-8",
    )
    return ExecutionEnvironment(
        root=tmpdir,
        implementation_file=impl,
        test_file=test_file,
        pythonpath=[str(tmpdir), project_root],
    )


def _exec(command: list[str], env: ExecutionEnvironment, timeout: int = 60) -> ProcessResult:
    e = os.environ.copy()
    e["PYTHONPATH"] = ":".join(env.pythonpath)
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=str(env.root), env=e, timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _exec_dir(command: list[str], directory: str, timeout: int = 60) -> ProcessResult:
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=directory, timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _rel(path: str, env: ExecutionEnvironment) -> str:
    try:
        return str(Path(path).relative_to(env.root))
    except ValueError:
        return path


_MYPY_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<severity>error|warning|note):\s*"
    r"(?P<message>.+?)(?:\s+\[(?P<code>[^\]]+)\])?$"
)


def _parse_mypy_output(output: str, root: Path | None = None) -> list[GateError]:
    errors = []
    for line in output.splitlines():
        m = _MYPY_PATTERN.match(line.strip())
        if not m or m.group("severity") == "note":
            continue
        file_path = m.group("file")
        if root:
            try:
                file_path = str(Path(file_path).relative_to(root))
            except ValueError:
                pass
        errors.append(GateError(
            message=m.group("message").strip(),
            file=file_path,
            line=int(m.group("line")), column=None,
            code=m.group("code"), severity=m.group("severity"),
        ))
    return errors


def _parse_ruff_json(stdout: str, root: Path | None = None) -> list[GateError]:
    errors: list[GateError] = []
    if not stdout.strip():
        return errors
    try:
        lint_results: list[Any] = json.loads(stdout)
        for f in lint_results:
            file_path = f["filename"]
            if root:
                try:
                    file_path = str(Path(file_path).relative_to(root))
                except ValueError:
                    pass
            errors.append(GateError(
                message=f["message"],
                file=file_path,
                line=f["location"]["row"], column=f["location"]["column"],
                code=f["code"],
                severity="error" if f["code"].startswith(("E", "F")) else "warning",
            ))
    except (json.JSONDecodeError, KeyError):
        pass
    return errors


def _parse_bandit_json(stdout: str, root: Path | None = None) -> list[GateError]:
    errors: list[GateError] = []
    if not stdout.strip():
        return errors
    try:
        bandit_out: dict[str, Any] = json.loads(stdout)
        for r in bandit_out.get("results", []):
            file_path = r["filename"]
            if root:
                try:
                    file_path = str(Path(file_path).relative_to(root))
                except ValueError:
                    pass
            errors.append(GateError(
                message=f"{r['test_name']}: {r['issue_text']}",
                file=file_path,
                line=r["line_number"], column=None,
                code=r["test_id"], severity="error",
            ))
    except (json.JSONDecodeError, KeyError):
        pass
    return errors


# ── Text mode gates ───────────────────────────────────────────────────────────

def _syntax_gate(implementation: str, tests: str) -> GateResult:
    start = time.monotonic()
    errors = []
    for label, source in [("implementation", implementation), ("tests", tests)]:
        try:
            ast.parse(source)
        except SyntaxError as e:
            errors.append(GateError(
                message=e.msg, file=label, line=e.lineno,
                column=e.offset, code="SyntaxError", severity="error",
            ))
    return GateResult(
        gate="syntax", passed=not errors, errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _type_check_gate(env: ExecutionEnvironment, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("typecheck", 60) if config else 60
    try:
        result = _exec([
            sys.executable, "-m", "mypy",
            str(env.implementation_file),
            "--ignore-missing-imports", "--no-error-summary",
            "--show-column-numbers", "--no-color-output",
        ], env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check", timeout)
    errors = _parse_mypy_output(result.output, env.root)
    if result.returncode != 0 and not errors:
        errors.append(GateError(
            message=result.output[:500] or "mypy exited non-zero (tool may not be installed)",
            file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
        ))
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _lint_gate(env: ExecutionEnvironment, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec([
            sys.executable, "-m", "ruff", "check",
            str(env.implementation_file),
            "--output-format", "json",
            "--select", "E,F,W,I",
            "--ignore", "E501",
        ], env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint", timeout)
    errors = _parse_ruff_json(result.stdout, env.root)
    if result.returncode != 0 and not errors:
        errors.append(GateError(
            message=result.output[:500] or "ruff exited non-zero (tool may not be installed)",
            file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
        ))
    return GateResult(
        gate="lint",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _test_gate(env: ExecutionEnvironment, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("test", 120) if config else 120
    try:
        result = _exec([
            sys.executable, "-m", "pytest",
            str(env.test_file), "--tb=short", "--no-header", "-q",
        ], env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors: list[GateError] = []
    current: str | None
    lines: list[str]
    current, lines = None, []
    for line in result.output.splitlines():
        if line.startswith("FAILED"):
            if current and lines:
                errors.append(GateError(
                    message=f"{current}: {' | '.join(lines)}",
                    file="tests", line=None, column=None,
                    code="TEST_FAILURE", severity="error",
                ))
            current = line.split("::")[1].split(" ")[0] if "::" in line else line
            lines = []
        elif line.startswith("E ") and current:
            lines.append(line[2:].strip())
    if current and lines:
        errors.append(GateError(
            message=f"{current}: {' | '.join(lines)}",
            file="tests", line=None, column=None,
            code="TEST_FAILURE", severity="error",
        ))
    if not errors:
        errors.append(GateError(
            message=result.output[:800], file="tests",
            line=None, column=None, code="TEST_FAILURE", severity="error",
        ))
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def _security_gate(env: ExecutionEnvironment, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("security", 60) if config else 60
    try:
        result = _exec([
            sys.executable, "-m", "bandit",
            str(env.implementation_file),
            "-f", "json", "--severity-level", "medium",
        ], env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("security", timeout)
    errors = _parse_bandit_json(result.stdout, env.root)
    if result.returncode not in (0, 1) and not errors:
        errors.append(GateError(
            message=result.output[:500] or "bandit exited non-zero (tool may not be installed)",
            file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
        ))
    return GateResult(
        gate="security",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def run_python_suite(
    implementation: str, tests: str, project_root: str,
    config: GateTimeoutConfig | None = None,
) -> list[GateResult]:
    """Text mode: syntax → type_check → lint → tests → security (temp dir)."""
    results = []
    syntax = _syntax_gate(implementation, tests)
    results.append(syntax)
    if not syntax.passed:
        return results

    env = _make_env(implementation, tests, project_root)
    try:
        for gate_fn in [_type_check_gate, _lint_gate, _test_gate, _security_gate]:
            result = gate_fn(env, config)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)

    return results


# ── Directory mode gates ──────────────────────────────────────────────────────

def _lint_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    """Directory mode lint — also catches syntax errors via ruff E999."""
    start = time.monotonic()
    root = Path(directory)
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec_dir([
            sys.executable, "-m", "ruff", "check", ".",
            "--output-format", "json",
            "--select", "E,F,W,I",
            "--ignore", "E501",
        ], directory, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint", timeout)
    errors = _parse_ruff_json(result.stdout, root)
    append_tool_error_if_silent(errors, result.returncode, result.output)
    return GateResult(
        gate="lint",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _type_check_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    root = Path(directory)
    timeout = config.timeout_for("typecheck", 60) if config else 60
    try:
        result = _exec_dir([
            sys.executable, "-m", "mypy", ".",
            "--ignore-missing-imports", "--no-error-summary",
            "--show-column-numbers", "--no-color-output",
        ], directory, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check", timeout)
    errors = _parse_mypy_output(result.output, root)
    append_tool_error_if_silent(errors, result.returncode, result.output)
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _test_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("test", 180) if config else 180
    try:
        result = _exec_dir([
            sys.executable, "-m", "pytest", "--tb=short", "--no-header", "-q",
        ], directory, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors: list[GateError] = []
    current: str | None
    lines: list[str]
    current, lines = None, []
    for line in result.output.splitlines():
        if line.startswith("FAILED"):
            if current and lines:
                errors.append(GateError(
                    message=f"{current}: {' | '.join(lines)}",
                    file=None, line=None, column=None,
                    code="TEST_FAILURE", severity="error",
                ))
            current = line.split("::")[1].strip() if "::" in line else line.strip()
            lines = []
        elif line.startswith("E ") and current:
            lines.append(line[2:].strip())
    if current and lines:
        errors.append(GateError(
            message=f"{current}: {' | '.join(lines)}",
            file=None, line=None, column=None,
            code="TEST_FAILURE", severity="error",
        ))
    if not errors:
        errors.append(GateError(
            message=result.output[:800], file=None,
            line=None, column=None, code="TEST_FAILURE", severity="error",
        ))
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def _security_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    root = Path(directory)
    timeout = config.timeout_for("security", 60) if config else 60
    bandit_cmd = [
        sys.executable, "-m", "bandit", "-r", ".",
        "-f", "json", "--severity-level", "medium",
        "--exclude", ".venv,venv,node_modules,.git",
    ]
    if (root / "pyproject.toml").exists():
        bandit_cmd += ["-c", str(root / "pyproject.toml")]
    try:
        result = _exec_dir(bandit_cmd, directory, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("security", timeout)
    errors = _parse_bandit_json(result.stdout, root)
    append_tool_error_if_silent(errors, result.returncode, result.output, success_codes=(0, 1))
    return GateResult(
        gate="security",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def run_python_suite_on_dir(
    directory: str, fail_fast: bool = True,
    config: GateTimeoutConfig | None = None,
    overrides: dict[str, list[str]] | None = None,
) -> list[GateResult]:
    """Directory mode: lint → type_check → tests → security (actual project dir).

    An ``overrides`` entry (gate-name -> argv) replaces that gate's default command
    with the operator-supplied one; absent keys run the default gate.
    """
    results = []
    gates: list[tuple[str, Any]] = [
        ("lint", _lint_gate_dir), ("type_check", _type_check_gate_dir),
        ("test", _test_gate_dir), ("security", _security_gate_dir),
    ]
    for name, gate_fn in gates:
        if overrides and name in overrides:
            result = _run_override_gate(name, overrides[name], directory, config)
        else:
            result = gate_fn(directory, config)
        results.append(result)
        if not result.passed and fail_fast:
            return results
    return results
