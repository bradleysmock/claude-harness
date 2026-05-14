"""
Python gate suite: syntax, type_check, lint, test, security.
"""

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
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..models import GateError, GateResult, GeneratedArtifact
from .base import BaseGate as _BaseGate, ProcessResult, run_process


# ── Execution environment ─────────────────────────────────────────────────────

@dataclass
class ExecutionEnvironment:
    root: Path
    implementation_file: Path
    test_file: Path
    pythonpath: list[str]

    @classmethod
    @contextmanager
    def create(cls, artifact: GeneratedArtifact, project_root: str):
        tmpdir = Path(tempfile.mkdtemp(prefix="harness_"))
        try:
            impl = tmpdir / "implementation.py"
            tests = tmpdir / "test_implementation.py"
            impl.write_text(artifact.implementation, encoding="utf-8")
            tests.write_text(
                f"import sys\n"
                f"sys.path.insert(0, '{tmpdir}')\n"
                f"sys.path.insert(0, '{project_root}')\n\n"
                + artifact.tests,
                encoding="utf-8",
            )
            yield cls(
                root=tmpdir,
                implementation_file=impl,
                test_file=tests,
                pythonpath=[str(tmpdir), project_root],
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── Subprocess helper ─────────────────────────────────────────────────────────

@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        return (self.stdout + "\n" + self.stderr).strip()


# ── Base gate ─────────────────────────────────────────────────────────────────

class BaseGate(_BaseGate):
    DEFAULT_TIMEOUT = 30

    @property
    @abstractmethod
    def gate_name(self) -> str: ...

    @abstractmethod
    def _command(self, env: ExecutionEnvironment) -> list[str]: ...

    @abstractmethod
    def _parse_errors(self, result: ProcessResult,
                      env: ExecutionEnvironment) -> list[GateError]: ...

    def run(self, artifact: GeneratedArtifact,
            env: ExecutionEnvironment) -> GateResult:
        start = time.monotonic()
        try:
            result = self._exec(self._command(env), env)
        except subprocess.TimeoutExpired:
            return GateResult(
                gate=self.gate_name, passed=False,
                errors=[GateError(
                    message=f"Timed out after {self.DEFAULT_TIMEOUT}s",
                    file=None, line=None, column=None,
                    code="TIMEOUT", severity="error",
                )],
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        errors = self._parse_errors(result, env)
        return GateResult(
            gate=self.gate_name,
            passed=result.returncode == 0 and not errors,
            errors=errors,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def _exec(self, command: list[str], env: ExecutionEnvironment) -> ProcessResult:
        e = os.environ.copy()
        e["PYTHONPATH"] = ":".join(env.pythonpath)
        p = subprocess.run(
            command, capture_output=True, text=True,
            cwd=str(env.root), env=e, timeout=self.DEFAULT_TIMEOUT,
        )
        return ProcessResult(p.stdout, p.stderr, p.returncode)

    def _rel(self, path: str, env: ExecutionEnvironment) -> str:
        try:
            return str(Path(path).relative_to(env.root))
        except ValueError:
            return path


# ── Gate 1: Syntax ────────────────────────────────────────────────────────────

class SyntaxGate(BaseGate):
    gate_name = "syntax"

    def _command(self, env): return []

    def run(self, artifact: GeneratedArtifact, env: ExecutionEnvironment) -> GateResult:
        start = time.monotonic()
        errors = []
        for label, source in [("implementation", artifact.implementation),
                               ("tests", artifact.tests)]:
            try:
                ast.parse(source)
            except SyntaxError as e:
                errors.append(GateError(
                    message=e.msg, file=label, line=e.lineno,
                    column=e.offset, code="SyntaxError", severity="error",
                ))
        return GateResult(
            gate=self.gate_name, passed=not errors, errors=errors,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def _parse_errors(self, result, env): return []


# ── Gate 2: Type check ────────────────────────────────────────────────────────

class TypeCheckGate(BaseGate):
    gate_name = "type_check"

    _PATTERN = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<severity>error|warning|note):\s*"
        r"(?P<message>.+?)(?:\s+\[(?P<code>[^\]]+)\])?$"
    )

    def _command(self, env):
        return [
            sys.executable, "-m", "mypy",
            str(env.implementation_file),
            "--ignore-missing-imports", "--no-error-summary",
            "--show-column-numbers", "--no-color-output",
        ]

    def _parse_errors(self, result, env):
        errors = []
        for line in result.output.splitlines():
            m = self._PATTERN.match(line.strip())
            if not m or m.group("severity") == "note":
                continue
            errors.append(GateError(
                message=m.group("message").strip(),
                file=self._rel(m.group("file"), env),
                line=int(m.group("line")), column=None,
                code=m.group("code"), severity=m.group("severity"),
            ))
        return errors


# ── Gate 3: Lint ──────────────────────────────────────────────────────────────

class LintGate(BaseGate):
    gate_name = "lint"

    def _command(self, env):
        return [
            sys.executable, "-m", "ruff", "check",
            str(env.implementation_file),
            "--output-format", "json",
            "--select", "E,F,W,I",
            "--ignore", "E501",
        ]

    def _parse_errors(self, result, env):
        if not result.stdout.strip():
            return []
        try:
            findings = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        return [
            GateError(
                message=f["message"],
                file=self._rel(f["filename"], env),
                line=f["location"]["row"], column=f["location"]["column"],
                code=f["code"],
                severity="error" if f["code"].startswith(("E","F")) else "warning",
            )
            for f in findings
        ]


# ── Gate 4: Tests ─────────────────────────────────────────────────────────────

class TestGate(BaseGate):
    gate_name = "test"
    DEFAULT_TIMEOUT = 60

    def _command(self, env):
        return [
            sys.executable, "-m", "pytest",
            str(env.test_file), "--tb=short", "--no-header", "-q",
        ]

    def _parse_errors(self, result, env):
        if result.returncode == 0:
            return []
        errors = []
        current, lines = None, []

        for line in result.output.splitlines():
            if line.startswith("FAILED"):
                if current and lines:
                    errors.append(self._fail(current, lines))
                current = line.split("::")[1].split(" ")[0] if "::" in line else line
                lines = []
            elif line.startswith("E ") and current:
                lines.append(line[2:].strip())

        if current and lines:
            errors.append(self._fail(current, lines))

        if not errors:
            errors.append(GateError(
                message=result.output[:800], file="tests",
                line=None, column=None, code="TEST_FAILURE", severity="error",
            ))
        return errors

    def _fail(self, name, lines):
        return GateError(
            message=f"{name}: {' | '.join(lines)}",
            file="tests", line=None, column=None,
            code="TEST_FAILURE", severity="error",
        )


# ── Gate 5: Security ──────────────────────────────────────────────────────────

class SecurityGate(BaseGate):
    gate_name = "security"

    def _command(self, env):
        return [
            sys.executable, "-m", "bandit",
            str(env.implementation_file),
            "-f", "json", "-l", "--severity-level", "medium",
        ]

    def _parse_errors(self, result, env):
        if not result.stdout.strip():
            return []
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        return [
            GateError(
                message=f"{r['test_name']}: {r['issue_text']}",
                file=self._rel(r["filename"], env),
                line=r["line_number"], column=None,
                code=r["test_id"], severity="error",
            )
            for r in report.get("results", [])
        ]


# ── Adapter wrapper ───────────────────────────────────────────────────────────

class PythonGate:
    """Binds a BaseGate to a specific ExecutionEnvironment. Satisfies ExecutionAdapter."""

    def __init__(self, inner: BaseGate, env: ExecutionEnvironment):
        self._inner = inner
        self._env = env

    @property
    def gate_name(self) -> str:
        return self._inner.gate_name

    def run(self, artifact: GeneratedArtifact) -> GateResult:
        return self._inner.run(artifact, self._env)


def default_python_gate_classes() -> list[BaseGate]:
    """Ordered cheapest → most expensive."""
    return [SyntaxGate(), TypeCheckGate(), LintGate(), TestGate(), SecurityGate()]
