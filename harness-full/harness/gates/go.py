"""
Go gate suite.

Gates (in order):
  1. build       go build ./...     compile check
  2. vet         go vet ./...       suspicious construct detection
  3. staticcheck staticcheck ./...  correctness + style (optional)
  4. test        go test ./...      unit tests with race detector

Tool requirements
─────────────────
Required:  go  (https://go.dev/dl/)
Optional:  staticcheck  (go install honnef.co/go/tools/cmd/staticcheck@latest)
           staticcheck gate is skipped if the binary is not found.

Execution environment
─────────────────────
A minimal Go module is created in the temp directory:
  tmpdir/
  ├── go.mod              (module harness/temp)
  ├── implementation.go
  └── implementation_test.go

The generated implementation must declare `package main` (or another
consistent package). The test file must declare the matching package
and import "testing".
"""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..models import GateError, GateResult, GeneratedArtifact
from .base import BaseGate, ProcessResult, run_process, require_tool


# ── Execution environment ─────────────────────────────────────────────────────

_GO_MOD_TEMPLATE = """\
module harness/temp

go 1.21
"""


@dataclass
class GoEnv:
    root: Path
    impl_file: Path
    test_file: Path

    @classmethod
    @contextmanager
    def create(cls, artifact: GeneratedArtifact, project_root: str):
        require_tool("go", hint="https://go.dev/dl/")
        tmpdir = Path(tempfile.mkdtemp(prefix="harness_go_"))
        try:
            (tmpdir / "go.mod").write_text(_GO_MOD_TEMPLATE)
            impl = tmpdir / "implementation.go"
            test = tmpdir / "implementation_test.go"
            impl.write_text(artifact.implementation, encoding="utf-8")
            test.write_text(artifact.tests, encoding="utf-8")
            yield cls(root=tmpdir, impl_file=impl, test_file=test)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── Shared error pattern ──────────────────────────────────────────────────────

# ./file.go:line:col: message   OR   file.go:line:col: message
_GO_ERROR = re.compile(
    r"^(?:\./)?(?P<file>[^:]+\.go):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?P<msg>.+)$"
)


def _parse_go_errors(output: str, env: GoEnv) -> list[GateError]:
    errors = []
    for line in output.splitlines():
        m = _GO_ERROR.match(line.strip())
        if not m:
            continue
        errors.append(GateError(
            message=m.group("msg").strip(),
            file=m.group("file"),
            line=int(m.group("line")),
            column=int(m.group("col")) if m.group("col") else None,
            code=None,
            severity="error",
        ))
    return errors


# ── Gate 1: Build ─────────────────────────────────────────────────────────────

class GoBuildGate(BaseGate):
    gate_name = "build"
    DEFAULT_TIMEOUT = 30

    def _command(self, env: GoEnv) -> list[str]:
        return ["go", "build", "./..."]

    def _parse_errors(self, result: ProcessResult, env: GoEnv) -> list[GateError]:
        return _parse_go_errors(result.output, env)


# ── Gate 2: Vet ───────────────────────────────────────────────────────────────

class GoVetGate(BaseGate):
    gate_name = "vet"
    DEFAULT_TIMEOUT = 30

    def _command(self, env: GoEnv) -> list[str]:
        return ["go", "vet", "./..."]

    def _parse_errors(self, result: ProcessResult, env: GoEnv) -> list[GateError]:
        return _parse_go_errors(result.output, env)


# ── Gate 3: Staticcheck (optional) ───────────────────────────────────────────

class GoStaticcheckGate(BaseGate):
    gate_name = "staticcheck"
    DEFAULT_TIMEOUT = 30

    # SA1000: message (file.go:line:col)
    _PATTERN = re.compile(
        r"^(?P<file>[^:]+\.go):(?P<line>\d+):(?P<col>\d+):\s*"
        r"(?P<msg>.+?)\s+\((?P<code>S[A-Z]\d+)\)$"
    )

    def _command(self, env: GoEnv) -> list[str]:
        return ["staticcheck", "./..."]

    def run(self, artifact: GeneratedArtifact, env: GoEnv) -> GateResult:
        import shutil as _shutil
        if not _shutil.which("staticcheck"):
            # Gracefully skip if not installed
            return GateResult(
                gate=self.gate_name, passed=True,
                errors=[],
                duration_ms=0,
            )
        return super().run(artifact, env)

    def _parse_errors(self, result: ProcessResult, env: GoEnv) -> list[GateError]:
        errors = []
        for line in result.output.splitlines():
            m = self._PATTERN.match(line.strip())
            if m:
                errors.append(GateError(
                    message=m.group("msg").strip(),
                    file=m.group("file"),
                    line=int(m.group("line")),
                    column=int(m.group("col")),
                    code=m.group("code"),
                    severity="error",
                ))
            elif line.strip() and not line.startswith("#"):
                # Fallback: unstructured staticcheck output
                fe = _parse_go_errors(line, env)
                errors.extend(fe)
        return errors


# ── Gate 4: Tests ─────────────────────────────────────────────────────────────

class GoTestGate(BaseGate):
    gate_name = "test"
    DEFAULT_TIMEOUT = 60

    def _command(self, env: GoEnv) -> list[str]:
        return ["go", "test", "-race", "-v", "./..."]

    def _parse_errors(self, result: ProcessResult, env: GoEnv) -> list[GateError]:
        if result.returncode == 0:
            return []
        errors = []
        current_test: str | None = None
        fail_lines: list[str] = []

        for line in result.output.splitlines():
            if line.startswith("--- FAIL:"):
                # e.g.  --- FAIL: TestGetUser (0.00s)
                current_test = line.split(":")[1].strip().split(" ")[0]
                fail_lines = []
            elif line.startswith("    ") and current_test:
                fail_lines.append(line.strip())
            elif line.startswith("FAIL") and current_test:
                errors.append(GateError(
                    message=f"{current_test}: {' | '.join(fail_lines[:3])}",
                    file="implementation_test.go",
                    line=None, column=None,
                    code="TEST_FAILURE", severity="error",
                ))
                current_test = None

        if current_test and fail_lines:
            errors.append(GateError(
                message=f"{current_test}: {' | '.join(fail_lines[:3])}",
                file="implementation_test.go",
                line=None, column=None,
                code="TEST_FAILURE", severity="error",
            ))

        if not errors and result.returncode != 0:
            # compile error surfaced by go test
            compile_errs = _parse_go_errors(result.output, env)
            errors.extend(compile_errs or [GateError(
                message=result.output[:600],
                file="implementation.go",
                line=None, column=None,
                code="BUILD_FAILURE", severity="error",
            )])

        return errors


# ── Suite ─────────────────────────────────────────────────────────────────────

class GoGate:
    """Binds a BaseGate to a GoEnv. Satisfies ExecutionAdapter."""

    def __init__(self, inner: BaseGate, env: GoEnv):
        self._inner = inner
        self._env = env

    @property
    def gate_name(self) -> str:
        return self._inner.gate_name

    def run(self, artifact: GeneratedArtifact) -> GateResult:
        return self._inner.run(artifact, self._env)


def go_gate_classes() -> list[BaseGate]:
    """Ordered cheapest → most expensive."""
    return [GoBuildGate(), GoVetGate(), GoStaticcheckGate(), GoTestGate()]
