from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from gates import GateTimeoutConfig, ProcessResult, _run_override_gate, _timeout_error
from models import GateError, GateResult

# Tools this gate invokes via subprocess (see gates/python.py REQUIRED_TOOLS for
# the doctor contract). Every name must appear in a subprocess argument list.
REQUIRED_TOOLS: list[str] = ["go", "staticcheck"]

_GO_MOD = "module harness/temp\n\ngo 1.21\n"

_GO_ERROR = re.compile(
    r"^(?:\./)?(?P<file>[^:]+\.go):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?P<msg>.+)$"
)

_STATICCHECK_PATTERN = re.compile(
    r"^(?P<file>[^:]+\.go):(?P<line>\d+):(?P<col>\d+):\s*(?P<msg>.+?)\s+\((?P<code>S[A-Z]\d+)\)$"
)


@dataclass
class GoEnv:
    root: Path
    impl_file: Path
    test_file: Path


def _make_env(implementation: str, tests: str, project_root: str) -> GoEnv:
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_go_"))
    (tmpdir / "go.mod").write_text(_GO_MOD)
    impl = tmpdir / "implementation.go"
    test = tmpdir / "implementation_test.go"
    impl.write_text(implementation, encoding="utf-8")
    test.write_text(tests, encoding="utf-8")
    return GoEnv(root=tmpdir, impl_file=impl, test_file=test)


def _exec(command: list[str], cwd: str | Path, timeout: int = 60) -> ProcessResult:
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=str(cwd), timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _parse_go_errors(output: str) -> list[GateError]:
    errors = []
    for line in output.splitlines():
        m = _GO_ERROR.match(line.strip())
        if m:
            errors.append(GateError(
                message=m.group("msg").strip(),
                file=m.group("file"),
                line=int(m.group("line")),
                column=int(m.group("col")) if m.group("col") else None,
                code=None, severity="error",
            ))
    return errors


# ── Text mode gates ───────────────────────────────────────────────────────────

def _build_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("typecheck", 60) if config else 60
    try:
        result = _exec(["go", "build", "./..."], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("build", timeout)
    errors = _parse_go_errors(result.output)
    return GateResult(gate="build", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _vet_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec(["go", "vet", "./..."], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("vet", timeout)
    errors = _parse_go_errors(result.output)
    return GateResult(gate="vet", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _staticcheck_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    import shutil as _shutil
    if not _shutil.which("staticcheck"):
        return GateResult(gate="staticcheck", passed=True, errors=[], duration_ms=0)
    start = time.monotonic()
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec(["staticcheck", "./..."], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("staticcheck", timeout)
    errors = []
    for line in result.output.splitlines():
        m = _STATICCHECK_PATTERN.match(line.strip())
        if m:
            errors.append(GateError(
                message=m.group("msg").strip(), file=m.group("file"),
                line=int(m.group("line")), column=int(m.group("col")),
                code=m.group("code"), severity="error",
            ))
        elif line.strip() and not line.startswith("#"):
            errors.extend(_parse_go_errors(line))
    return GateResult(gate="staticcheck", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _test_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("test", 120) if config else 120
    try:
        result = _exec(["go", "test", "-race", "-v", "./..."], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors = []
    current_test: str | None = None
    fail_lines: list[str] = []
    for line in result.output.splitlines():
        if line.startswith("--- FAIL:"):
            current_test = line.split(":")[1].strip().split(" ")[0]
            fail_lines = []
        elif line.startswith("    ") and current_test:
            fail_lines.append(line.strip())
        elif line.startswith("FAIL") and current_test:
            errors.append(GateError(
                message=f"{current_test}: {' | '.join(fail_lines[:3])}",
                file=None, line=None, column=None,
                code="TEST_FAILURE", severity="error",
            ))
            current_test = None
    if current_test and fail_lines:
        errors.append(GateError(
            message=f"{current_test}: {' | '.join(fail_lines[:3])}",
            file=None, line=None, column=None,
            code="TEST_FAILURE", severity="error",
        ))
    if not errors:
        compile_errs = _parse_go_errors(result.output)
        errors = compile_errs or [GateError(
            message=result.output[:600], file=None,
            line=None, column=None, code="BUILD_FAILURE", severity="error",
        )]
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def run_go_suite(
    implementation: str, tests: str, project_root: str,
    config: GateTimeoutConfig | None = None,
) -> list[GateResult]:
    """Text mode: build → vet → staticcheck → test (temp dir)."""
    env = _make_env(implementation, tests, project_root)
    results = []
    try:
        for gate_fn in [_build_gate, _vet_gate, _staticcheck_gate, _test_gate]:
            result = gate_fn(env.root, config)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    return results


# ── Directory mode gates ──────────────────────────────────────────────────────

def run_go_suite_on_dir(
    directory: str, fail_fast: bool = True,
    config: GateTimeoutConfig | None = None,
    overrides: dict[str, list[str]] | None = None,
) -> list[GateResult]:
    """Directory mode: build → vet → test (actual project dir, no temp env).

    An ``overrides`` entry (gate-name -> argv) replaces that gate's default command
    with the operator-supplied one; absent keys run the default gate.
    """
    results = []
    gates = [("build", _build_gate), ("vet", _vet_gate), ("test", _test_gate)]
    for name, gate_fn in gates:
        if overrides and name in overrides:
            result = _run_override_gate(name, overrides[name], directory, config)
        else:
            result = gate_fn(directory, config)
        results.append(result)
        if not result.passed and fail_fast:
            return results
    return results
