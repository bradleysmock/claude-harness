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
    """Text mode: run gates on generated code in a temp dir (fail-fast)."""
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


def run_suite_on_dir(
    language: str,
    directory: str,
    fail_fast: bool = True,
) -> list[GateResult]:
    """Directory mode: run gates on actual project files (worktree or project dir)."""
    if language == "python":
        from gates.python import run_python_suite_on_dir
        return run_python_suite_on_dir(directory, fail_fast=fail_fast)
    elif language == "typescript":
        from gates.typescript import run_typescript_suite_on_dir
        return run_typescript_suite_on_dir(directory, fail_fast=fail_fast)
    elif language == "go":
        from gates.go import run_go_suite_on_dir
        return run_go_suite_on_dir(directory, fail_fast=fail_fast)
    elif language == "rust":
        from gates.rust import run_rust_suite_on_dir
        return run_rust_suite_on_dir(directory, fail_fast=fail_fast)
    else:
        raise ValueError(f"Unsupported language: {language!r}")
