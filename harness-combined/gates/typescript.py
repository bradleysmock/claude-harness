from __future__ import annotations
import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models import GateError, GateResult
from gates import ProcessResult, append_tool_error_if_silent, find_config_root


_TSCONFIG = json.dumps({
    "compilerOptions": {
        "target": "ES2020",
        "module": "commonjs",
        "lib": ["ES2020"],
        "strict": True,
        "esModuleInterop": True,
        "skipLibCheck": True,
        "outDir": "./dist",
        "rootDir": ".",
        "ignoreDeprecations": "6.0",
    },
    "include": ["./*.ts"],
    "exclude": ["node_modules", "dist"],
}, indent=2)

_ESLINT_CONFIG = json.dumps({
    "parser": "@typescript-eslint/parser",
    "plugins": ["@typescript-eslint"],
    "extends": ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
    "rules": {
        "no-console": "warn",
        "@typescript-eslint/no-explicit-any": "warn",
        "@typescript-eslint/explicit-function-return-type": "off",
    },
    "env": {"node": True, "es2020": True},
}, indent=2)

_JEST_CONFIG = json.dumps({
    "preset": "ts-jest",
    "testEnvironment": "node",
    "testMatch": ["**/*.test.ts"],
    "moduleFileExtensions": ["ts", "js"],
}, indent=2)

_PACKAGE_JSON = json.dumps({
    "name": "harness-temp",
    "version": "0.0.1",
    "private": True,
    "scripts": {"test": "jest", "lint": "eslint ."},
    "devDependencies": {
        "typescript": "*", "ts-jest": "*", "jest": "*", "@types/jest": "*",
        "eslint": "*", "@typescript-eslint/parser": "*",
        "@typescript-eslint/eslint-plugin": "*",
    },
}, indent=2)


@dataclass
class TypeScriptEnv:
    root: Path
    impl_file: Path
    test_file: Path


def _make_env(implementation: str, tests: str, project_root: str) -> TypeScriptEnv:
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_ts_"))
    (tmpdir / "tsconfig.json").write_text(_TSCONFIG)
    (tmpdir / ".eslintrc.json").write_text(_ESLINT_CONFIG)
    (tmpdir / "jest.config.json").write_text(_JEST_CONFIG)
    (tmpdir / "package.json").write_text(_PACKAGE_JSON)

    project_nm = Path(project_root) / "node_modules"
    tmp_nm = tmpdir / "node_modules"
    if project_nm.exists() and not tmp_nm.exists():
        tmp_nm.symlink_to(project_nm.resolve())

    impl = tmpdir / "implementation.ts"
    test = tmpdir / "implementation.test.ts"
    impl.write_text(implementation, encoding="utf-8")

    test_content = tests
    if "from './implementation'" not in test_content and 'from "./implementation"' not in test_content:
        test_content = "import * as impl from './implementation';\n\n" + test_content
    test.write_text(test_content, encoding="utf-8")

    return TypeScriptEnv(root=tmpdir, impl_file=impl, test_file=test)


def _exec(command: list[str], cwd: str | Path, timeout: int = 60) -> ProcessResult:
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=str(cwd), timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return path


def _timeout_error(gate: str) -> GateResult:
    return GateResult(
        gate=gate, passed=False,
        errors=[GateError(message="Timed out", file=None, line=None, column=None,
                          code="TIMEOUT", severity="error")],
        duration_ms=60000,
    )


_TSC_PATTERN = re.compile(
    r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s*"
    r"(?P<severity>error|warning)\s+(?P<code>TS\d+):\s*(?P<msg>.+)$"
)


def _parse_tsc_errors(output: str, root: Path) -> list[GateError]:
    errors = []
    for line in output.splitlines():
        m = _TSC_PATTERN.match(line.strip())
        if not m:
            continue
        errors.append(GateError(
            message=m.group("msg").strip(),
            file=_rel(m.group("file"), root),
            line=int(m.group("line")), column=int(m.group("col")),
            code=m.group("code"), severity=m.group("severity"),
        ))
    return errors


def _parse_eslint_json(stdout: str, root: Path) -> list[GateError]:
    errors = []
    try:
        lint_results: list[Any] = json.loads(stdout or "[]")
        for file_result in lint_results:
            for msg in file_result.get("messages", []):
                sev = "error" if msg.get("severity", 1) == 2 else "warning"
                errors.append(GateError(
                    message=msg.get("message", ""),
                    file=_rel(file_result.get("filePath", ""), root),
                    line=msg.get("line"), column=msg.get("column"),
                    code=msg.get("ruleId"), severity=sev,
                ))
    except json.JSONDecodeError:
        pass
    return errors


# ── Text mode gates ───────────────────────────────────────────────────────────

def _type_check_gate_text(env: TypeScriptEnv) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec(["npx", "--yes", "tsc", "--noEmit", "--pretty", "false"], env.root)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check")
    errors = _parse_tsc_errors(result.output, env.root)
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _lint_gate_text(env: TypeScriptEnv) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec([
            "npx", "--yes", "eslint",
            str(env.impl_file),
            "--format", "json",
            "--no-eslintrc",
            "--config", str(env.root / ".eslintrc.json"),
        ], env.root)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint")
    errors = _parse_eslint_json(result.stdout, env.root)
    return GateResult(
        gate="lint",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _test_gate_text(env: TypeScriptEnv) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec([
            "npx", "--yes", "jest",
            "--no-coverage",
            "--testPathPattern", "implementation.test.ts",
            "--config", str(env.root / "jest.config.json"),
        ], env.root, timeout=120)
    except subprocess.TimeoutExpired:
        return _timeout_error("test")
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors = []
    current_test: str | None = None
    fail_lines: list[str] = []
    for line in result.output.splitlines():
        if line.strip().startswith("●"):
            if current_test and fail_lines:
                errors.append(GateError(
                    message=f"{current_test}: {' | '.join(fail_lines[:3])}",
                    file="implementation.test.ts", line=None, column=None,
                    code="TEST_FAILURE", severity="error",
                ))
            current_test = line.strip().lstrip("●").strip()
            fail_lines = []
        elif current_test and ("expect(" in line or "Expected" in line or "Received" in line):
            fail_lines.append(line.strip())
    if current_test and fail_lines:
        errors.append(GateError(
            message=f"{current_test}: {' | '.join(fail_lines[:3])}",
            file="implementation.test.ts", line=None, column=None,
            code="TEST_FAILURE", severity="error",
        ))
    if not errors:
        errors.append(GateError(
            message=result.output[:600], file="implementation.test.ts",
            line=None, column=None, code="TEST_FAILURE", severity="error",
        ))
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def run_typescript_suite(
    implementation: str, tests: str, project_root: str
) -> list[GateResult]:
    """Text mode: type_check → lint → tests (temp dir)."""
    env = _make_env(implementation, tests, project_root)
    results = []
    try:
        for gate_fn in [_type_check_gate_text, _lint_gate_text, _test_gate_text]:
            result = gate_fn(env)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    return results


# ── Directory mode gates ──────────────────────────────────────────────────────

_TSCONFIG_NAMES = ("tsconfig.json",)
_ESLINT_CONFIG_NAMES = (
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
    ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.yml", ".eslintrc",
)
_JEST_CONFIG_NAMES = (
    "jest.config.js", "jest.config.cjs", "jest.config.mjs",
    "jest.config.ts", "jest.config.json",
)


def _changed_test_files(jest_root: Path, base: str = "main") -> list[str] | None:
    """Test files changed vs the merge-base with ``base``, relative to ``jest_root``.

    Returns a list of changed ``*.test.ts(x)`` paths, or ``None`` when scoping
    cannot be determined (git missing, not a repo, base unknown). Callers must
    treat ``None`` as "fall back to the full suite" — never as "skip all".
    """
    if shutil.which("git") is None:
        return None
    try:
        mb = subprocess.run(
            ["git", "-C", str(jest_root), "merge-base", "HEAD", base],
            capture_output=True, text=True, timeout=30,
        )
        ref = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base
        diff = subprocess.run(
            ["git", "-C", str(jest_root), "diff", "--name-only", ref],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if diff.returncode != 0:
        return None
    return [
        line.strip() for line in diff.stdout.splitlines()
        if line.strip().endswith((".test.ts", ".test.tsx"))
    ]


def _type_check_gate_dir(directory: str) -> GateResult:
    start = time.monotonic()
    root = find_config_root(Path(directory), _TSCONFIG_NAMES)
    try:
        result = _exec(["npx", "--yes", "tsc", "--noEmit", "--pretty", "false"], root)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check")
    errors = _parse_tsc_errors(result.output, root)
    append_tool_error_if_silent(errors, result.returncode, result.output)
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _lint_gate_dir(directory: str) -> GateResult:
    start = time.monotonic()
    root = find_config_root(Path(directory), _ESLINT_CONFIG_NAMES)
    try:
        result = _exec([
            "npx", "--yes", "eslint", ".", "--format", "json", "--ext", ".ts,.tsx",
        ], root)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint")
    errors = _parse_eslint_json(result.stdout, root)
    append_tool_error_if_silent(errors, result.returncode, result.output)
    return GateResult(
        gate="lint",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _test_gate_dir(directory: str) -> GateResult:
    start = time.monotonic()
    root = find_config_root(Path(directory), _JEST_CONFIG_NAMES)
    # Scope to the test files this ticket changed so an unrelated ticket's
    # (or broken pre-existing) test cannot fail the gate. Fail closed: if the
    # change set can't be determined, run the full suite rather than skip.
    scoped = _changed_test_files(root)
    cmd = ["npx", "--yes", "jest", "--no-coverage"]
    if scoped:
        cmd += scoped
    try:
        result = _exec(cmd, root, timeout=180)
    except subprocess.TimeoutExpired:
        return _timeout_error("test")
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors = []
    current_test: str | None = None
    fail_lines: list[str] = []
    for line in result.output.splitlines():
        if line.strip().startswith("●"):
            if current_test and fail_lines:
                errors.append(GateError(
                    message=f"{current_test}: {' | '.join(fail_lines[:3])}",
                    file=None, line=None, column=None,
                    code="TEST_FAILURE", severity="error",
                ))
            current_test = line.strip().lstrip("●").strip()
            fail_lines = []
        elif current_test and ("expect(" in line or "Expected" in line or "Received" in line):
            fail_lines.append(line.strip())
    if current_test and fail_lines:
        errors.append(GateError(
            message=f"{current_test}: {' | '.join(fail_lines[:3])}",
            file=None, line=None, column=None,
            code="TEST_FAILURE", severity="error",
        ))
    if not errors:
        errors.append(GateError(
            message=result.output[:600], file=None,
            line=None, column=None, code="TEST_FAILURE", severity="error",
        ))
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def run_typescript_suite_on_dir(
    directory: str, fail_fast: bool = True
) -> list[GateResult]:
    """Directory mode: type_check → lint → tests (actual project dir)."""
    results = []
    for gate_fn in [_type_check_gate_dir, _lint_gate_dir, _test_gate_dir]:
        result = gate_fn(directory)
        results.append(result)
        if not result.passed and fail_fast:
            return results
    return results
