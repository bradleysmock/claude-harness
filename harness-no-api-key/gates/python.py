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

from models import GateError, GateResult
from gates import ProcessResult


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


def _rel(path: str, env: ExecutionEnvironment) -> str:
    try:
        return str(Path(path).relative_to(env.root))
    except ValueError:
        return path


def _timeout_error(gate: str) -> GateResult:
    return GateResult(
        gate=gate, passed=False,
        errors=[GateError(message="Timed out", file=None, line=None, column=None,
                          code="TIMEOUT", severity="error")],
        duration_ms=60000,
    )


# ── Gate 1: Syntax ────────────────────────────────────────────────────────────

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


# ── Gate 2: Type check ────────────────────────────────────────────────────────

_MYPY_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<severity>error|warning|note):\s*"
    r"(?P<message>.+?)(?:\s+\[(?P<code>[^\]]+)\])?$"
)


def _type_check_gate(env: ExecutionEnvironment) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec([
            sys.executable, "-m", "mypy",
            str(env.implementation_file),
            "--ignore-missing-imports", "--no-error-summary",
            "--show-column-numbers", "--no-color-output",
        ], env)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check")
    errors = []
    for line in result.output.splitlines():
        m = _MYPY_PATTERN.match(line.strip())
        if not m or m.group("severity") == "note":
            continue
        errors.append(GateError(
            message=m.group("message").strip(),
            file=_rel(m.group("file"), env),
            line=int(m.group("line")), column=None,
            code=m.group("code"), severity=m.group("severity"),
        ))
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


# ── Gate 3: Lint ──────────────────────────────────────────────────────────────

def _lint_gate(env: ExecutionEnvironment) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec([
            sys.executable, "-m", "ruff", "check",
            str(env.implementation_file),
            "--output-format", "json",
            "--select", "E,F,W,I",
            "--ignore", "E501",
        ], env)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint")
    errors = []
    if result.stdout.strip():
        try:
            for f in json.loads(result.stdout):
                errors.append(GateError(
                    message=f["message"],
                    file=_rel(f["filename"], env),
                    line=f["location"]["row"], column=f["location"]["column"],
                    code=f["code"],
                    severity="error" if f["code"].startswith(("E", "F")) else "warning",
                ))
        except (json.JSONDecodeError, KeyError):
            pass
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


# ── Gate 4: Tests ─────────────────────────────────────────────────────────────

def _test_gate(env: ExecutionEnvironment) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec([
            sys.executable, "-m", "pytest",
            str(env.test_file), "--tb=short", "--no-header", "-q",
        ], env, timeout=120)
    except subprocess.TimeoutExpired:
        return _timeout_error("test")
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors = []
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


# ── Gate 5: Security ──────────────────────────────────────────────────────────

def _security_gate(env: ExecutionEnvironment) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec([
            sys.executable, "-m", "bandit",
            str(env.implementation_file),
            "-f", "json", "--severity-level", "medium",
        ], env)
    except subprocess.TimeoutExpired:
        return _timeout_error("security")
    errors = []
    if result.stdout.strip():
        try:
            for r in json.loads(result.stdout).get("results", []):
                errors.append(GateError(
                    message=f"{r['test_name']}: {r['issue_text']}",
                    file=_rel(r["filename"], env),
                    line=r["line_number"], column=None,
                    code=r["test_id"], severity="error",
                ))
        except (json.JSONDecodeError, KeyError):
            pass
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


# ── Suite ─────────────────────────────────────────────────────────────────────

def run_python_suite(
    implementation: str, tests: str, project_root: str
) -> list[GateResult]:
    results = []
    syntax = _syntax_gate(implementation, tests)
    results.append(syntax)
    if not syntax.passed:
        return results

    env = _make_env(implementation, tests, project_root)
    try:
        for gate_fn in [_type_check_gate, _lint_gate, _test_gate, _security_gate]:
            result = gate_fn(env)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)

    return results
