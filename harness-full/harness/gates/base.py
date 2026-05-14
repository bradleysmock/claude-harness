"""
Shared gate infrastructure.

BaseGate, ProcessResult, and the tool-availability check used by all adapters.
Language-specific environments live in their own modules.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..models import GateError, GateResult, GeneratedArtifact

log = logging.getLogger("harness.gates")


# ── Process helper ────────────────────────────────────────────────────────────

@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        return (self.stdout + "\n" + self.stderr).strip()


def run_process(
    command: list[str],
    cwd: str,
    extra_env: dict[str, str] | None = None,
    timeout: int = 60,
) -> ProcessResult:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True,
            cwd=cwd, env=env, timeout=timeout,
        )
        return ProcessResult(proc.stdout, proc.stderr, proc.returncode)
    except FileNotFoundError as e:
        raise ToolNotFoundError(str(command[0])) from e


def require_tool(name: str, hint: str = "") -> None:
    """Raise ToolNotFoundError if `name` is not on PATH."""
    if not shutil.which(name):
        raise ToolNotFoundError(name, hint)


class ToolNotFoundError(RuntimeError):
    def __init__(self, tool: str, hint: str = ""):
        msg = f"Required tool not found: '{tool}'"
        if hint:
            msg += f"\n  Install: {hint}"
        super().__init__(msg)
        self.tool = tool


# ── Base gate ─────────────────────────────────────────────────────────────────

class BaseGate(ABC):
    DEFAULT_TIMEOUT: int = 30

    @property
    @abstractmethod
    def gate_name(self) -> str: ...

    @abstractmethod
    def _command(self, env) -> list[str]: ...

    @abstractmethod
    def _parse_errors(self, result: ProcessResult, env) -> list[GateError]: ...

    def run(self, artifact: GeneratedArtifact, env) -> GateResult:
        start = time.monotonic()
        try:
            result = run_process(
                self._command(env),
                cwd=str(env.root),
                extra_env=getattr(env, "extra_env", None),
                timeout=self.DEFAULT_TIMEOUT,
            )
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
        except ToolNotFoundError as e:
            return GateResult(
                gate=self.gate_name, passed=False,
                errors=[GateError(
                    message=str(e), file=None, line=None, column=None,
                    code="TOOL_NOT_FOUND", severity="error",
                )],
                duration_ms=0,
            )
        errors = self._parse_errors(result, env)
        return GateResult(
            gate=self.gate_name,
            passed=result.returncode == 0 and not errors,
            errors=errors,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def _rel(self, path: str, env) -> str:
        try:
            return str(Path(path).relative_to(env.root))
        except ValueError:
            return path
