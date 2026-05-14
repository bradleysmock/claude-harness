"""
TypeScript gate suite.

Gates (in order):
  1. type_check   tsc --noEmit           syntax + types together
  2. lint         eslint --format=json   style and correctness
  3. test         jest / vitest          unit tests

Tool requirements
─────────────────
These must be resolvable via npx (comes with npm >= 5.2):
  - typescript       (tsc)
  - eslint
  - jest  OR  vitest

Fastest setup in any project:
  npm install -D typescript eslint jest ts-jest @types/jest

The execution environment creates a minimal tsconfig.json and writes
the generated implementation and test files. If the project root contains
a node_modules directory, it is symlinked into the temp dir so npm
packages are available without a fresh install.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..models import GateError, GateResult, GeneratedArtifact
from .base import BaseGate, ProcessResult, run_process

# ── Minimal scaffolding written into the temp environment ─────────────────────

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
        "baseUrl": ".",
    },
    "include": ["./*.ts"],
    "exclude": ["node_modules", "dist"],
}, indent=2)

_ESLINT_CONFIG = json.dumps({
    "parser": "@typescript-eslint/parser",
    "plugins": ["@typescript-eslint"],
    "extends": [
        "eslint:recommended",
        "plugin:@typescript-eslint/recommended",
    ],
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
        "typescript": "*",
        "ts-jest": "*",
        "jest": "*",
        "@types/jest": "*",
        "eslint": "*",
        "@typescript-eslint/parser": "*",
        "@typescript-eslint/eslint-plugin": "*",
    },
}, indent=2)


# ── Execution environment ─────────────────────────────────────────────────────

@dataclass
class TypeScriptEnv:
    root: Path
    impl_file: Path
    test_file: Path

    @classmethod
    @contextmanager
    def create(cls, artifact: GeneratedArtifact, project_root: str):
        tmpdir = Path(tempfile.mkdtemp(prefix="harness_ts_"))
        try:
            # Write scaffold
            (tmpdir / "tsconfig.json").write_text(_TSCONFIG)
            (tmpdir / ".eslintrc.json").write_text(_ESLINT_CONFIG)
            (tmpdir / "jest.config.json").write_text(_JEST_CONFIG)
            (tmpdir / "package.json").write_text(_PACKAGE_JSON)

            # Symlink node_modules from project if available (avoids npm install)
            project_nm = Path(project_root) / "node_modules"
            tmp_nm = tmpdir / "node_modules"
            if project_nm.exists() and not tmp_nm.exists():
                tmp_nm.symlink_to(project_nm.resolve())

            # Write generated files
            impl = tmpdir / "implementation.ts"
            test = tmpdir / "implementation.test.ts"
            impl.write_text(artifact.implementation, encoding="utf-8")

            # Ensure the test imports from the local implementation
            test_content = artifact.tests
            if "from './implementation'" not in test_content \
                    and 'from "./implementation"' not in test_content:
                test_content = (
                    "import * as impl from './implementation';\n\n"
                    + test_content
                )
            test.write_text(test_content, encoding="utf-8")

            yield cls(root=tmpdir, impl_file=impl, test_file=test)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── Gate 1: Type check (tsc) ──────────────────────────────────────────────────

class TypeScriptTypeCheckGate(BaseGate):
    gate_name = "type_check"
    DEFAULT_TIMEOUT = 30

    # file(line,col): error TS2345: message
    _PATTERN = re.compile(
        r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s*"
        r"(?P<severity>error|warning)\s+(?P<code>TS\d+):\s*(?P<msg>.+)$"
    )

    def _command(self, env: TypeScriptEnv) -> list[str]:
        return ["npx", "--yes", "tsc", "--noEmit", "--pretty", "false"]

    def _parse_errors(self, result: ProcessResult, env: TypeScriptEnv) -> list[GateError]:
        errors = []
        for line in result.output.splitlines():
            m = self._PATTERN.match(line.strip())
            if not m:
                continue
            errors.append(GateError(
                message=m.group("msg").strip(),
                file=self._rel(m.group("file"), env),
                line=int(m.group("line")),
                column=int(m.group("col")),
                code=m.group("code"),
                severity=m.group("severity"),
            ))
        return errors


# ── Gate 2: Lint (eslint) ─────────────────────────────────────────────────────

class TypeScriptLintGate(BaseGate):
    gate_name = "lint"
    DEFAULT_TIMEOUT = 30

    def _command(self, env: TypeScriptEnv) -> list[str]:
        return [
            "npx", "--yes", "eslint",
            str(env.impl_file),
            "--format", "json",
            "--no-eslintrc",
            "--config", str(env.root / ".eslintrc.json"),
        ]

    def _parse_errors(self, result: ProcessResult, env: TypeScriptEnv) -> list[GateError]:
        try:
            findings = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return []
        errors = []
        for file_result in findings:
            for msg in file_result.get("messages", []):
                sev = "error" if msg.get("severity", 1) == 2 else "warning"
                errors.append(GateError(
                    message=msg.get("message", ""),
                    file=self._rel(file_result.get("filePath", ""), env),
                    line=msg.get("line"),
                    column=msg.get("column"),
                    code=msg.get("ruleId"),
                    severity=sev,
                ))
        return errors


# ── Gate 3: Tests (jest) ──────────────────────────────────────────────────────

class TypeScriptTestGate(BaseGate):
    gate_name = "test"
    DEFAULT_TIMEOUT = 60

    def _command(self, env: TypeScriptEnv) -> list[str]:
        return [
            "npx", "--yes", "jest",
            "--no-coverage",
            "--testPathPattern", "implementation.test.ts",
            "--config", str(env.root / "jest.config.json"),
        ]

    def _parse_errors(self, result: ProcessResult, env: TypeScriptEnv) -> list[GateError]:
        if result.returncode == 0:
            return []
        errors = []
        current_test: str | None = None
        fail_lines: list[str] = []

        for line in result.output.splitlines():
            if line.strip().startswith("●"):
                if current_test and fail_lines:
                    errors.append(self._make_error(current_test, fail_lines))
                current_test = line.strip().lstrip("●").strip()
                fail_lines = []
            elif current_test and line.strip().startswith("expect("):
                fail_lines.append(line.strip())
            elif current_test and "Expected" in line or "Received" in line:
                fail_lines.append(line.strip())

        if current_test and fail_lines:
            errors.append(self._make_error(current_test, fail_lines))

        if not errors:
            errors.append(GateError(
                message=result.output[:600],
                file="implementation.test.ts",
                line=None, column=None,
                code="TEST_FAILURE", severity="error",
            ))
        return errors

    def _make_error(self, test: str, lines: list[str]) -> GateError:
        return GateError(
            message=f"{test}: {' | '.join(lines[:3])}",
            file="implementation.test.ts",
            line=None, column=None,
            code="TEST_FAILURE", severity="error",
        )


# ── Suite ─────────────────────────────────────────────────────────────────────

class TypeScriptGate:
    """Binds a BaseGate to a TypeScriptEnv. Satisfies ExecutionAdapter."""

    def __init__(self, inner: BaseGate, env: TypeScriptEnv):
        self._inner = inner
        self._env = env

    @property
    def gate_name(self) -> str:
        return self._inner.gate_name

    def run(self, artifact: GeneratedArtifact) -> GateResult:
        return self._inner.run(artifact, self._env)


def typescript_gate_classes() -> list[BaseGate]:
    """Ordered cheapest → most expensive."""
    return [
        TypeScriptTypeCheckGate(),
        TypeScriptLintGate(),
        TypeScriptTestGate(),
    ]
