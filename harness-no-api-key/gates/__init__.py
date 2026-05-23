from __future__ import annotations
from dataclasses import dataclass

from models import GateResult


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        return (self.stdout + "\n" + self.stderr).strip()


def run_suite_for(
    language: str,
    implementation: str,
    tests: str,
    project_root: str,
) -> list[GateResult]:
    if language == "python":
        from gates.python import run_python_suite
        return run_python_suite(implementation, tests, project_root)
    elif language == "typescript":
        from gates.typescript import run_typescript_suite
        return run_typescript_suite(implementation, tests, project_root)
    elif language == "go":
        from gates.go import run_go_suite
        return run_go_suite(implementation, tests, project_root)
    elif language == "rust":
        from gates.rust import run_rust_suite
        return run_rust_suite(implementation, tests, project_root)
    else:
        raise ValueError(f"Unsupported language: {language!r}")
